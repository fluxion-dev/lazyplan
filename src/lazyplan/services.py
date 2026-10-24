"""Application services: use-cases over Store.

Writes and policy go through here: creation (with templates), status
transitions, reconciliation, archival, import/export. Reads and plain
patch-writes may use Store directly (read-model bypass: no pass-through
bloat for policy-free paths). Stdlib only.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .forge import AuthStatus, Forge, RepoRef, detect_forge, parse_pull_url, resolve_auth
from .github import GitHubClient, GitHubError
from .kinds import check_kind
from .models import Milestone, Plan, Status, Task
from .store import Store, _ser
from .templates import apply_template, template_criteria
from .vcs import CommitInfo, RepoStatus, VCSBackend, detect_backend, origin_url

ARCHIVE_AFTER_SECS = 24 * 3600

_LAZYPLAN_TRAILER = re.compile(r"(?i)^lazyplan:\s*(.+)$")
_LAZYPLAN_REF = re.compile(r"(?i)^([ptm])\s*#?(\d+)$")
_LAZYPLAN_BRANCH = re.compile(r"^(task|plan|milestone)/(\d+)(?:-|$)")
_KIND_BY_LETTER = {"p": "plan", "m": "milestone", "t": "task"}
_LETTER_BY_KIND = {"plan": "P", "milestone": "M", "task": "T"}


# -- creation (template fill + auto-criteria live here, not in Store) ------
def create_plan(
    store: Store,
    name: str,
    description: str = "",
    goal: str = "",
    actor: str = "human",
) -> Plan:
    """Insert a plan with template defaults and auto-criteria."""
    filled = apply_template(
        "plan",
        {"title": name, "why": goal, "what": description},
        store.path,
    )
    p = store.add_plan(
        name=filled["title"].strip(),
        description=filled["what"],
        goal=filled["why"],
        actor=actor,
    )
    for text in template_criteria("plan", store.path):
        store.add_criteria("plan", p.id, text, actor=actor)
    return p


def create_milestone(
    store: Store,
    plan_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
) -> Milestone:
    """Insert a milestone with template defaults and auto-criteria."""
    filled = apply_template(
        "milestone",
        {"title": title, "desc": description},
        store.path,
    )
    s = store.add_milestone(
        plan_id=plan_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
    )
    for text in template_criteria("milestone", store.path):
        store.add_criteria("milestone", s.id, text, actor=actor)
    return s


def create_task(
    store: Store,
    milestone_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
) -> Task:
    """Insert a task with template defaults and auto-criteria."""
    filled = apply_template(
        "task",
        {"title": title, "desc": description},
        store.path,
    )
    t = store.add_task(
        milestone_id=milestone_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
    )
    for text in template_criteria("task", store.path):
        store.add_criteria("task", t.id, text, actor=actor)
    return t


# -- status (rollup policy lives here) --------------------------------------
def _rollup_target(statuses: list[Status]) -> Status:
    """Parent state from children: all done -> done, any doing -> doing, else todo."""
    if all(s == Status.DONE for s in statuses):
        return Status.DONE
    if any(s == Status.DOING for s in statuses):
        return Status.DOING
    return Status.TODO


def heal(store: Store, kind: str, obj_id: int, actor: str = "human") -> bool:
    """Recompute one milestone/plan from its children. Returns changed."""
    check_kind(kind)
    obj: Plan | Milestone | None
    if kind == "milestone":
        obj = store.get_milestone(obj_id)
        kids = [t.status for t in store.list_tasks(obj_id)] if obj is not None else []
    elif kind == "plan":
        obj = store.get_plan(obj_id)
        kids = [s.status for s in store.list_milestones(obj_id)] if obj is not None else []
    else:
        raise ValueError("kind must be milestone|plan")
    if obj is None or not kids:
        return False
    target = _rollup_target(kids)
    if obj.status == target:
        return False
    store.set_status_raw(kind, obj_id, target)
    store.log(actor, kind, "status", f"{kind} #{obj_id} -> {target.value} (rollup)")
    return True


def heal_parents(store: Store, kind: str, obj_id: int, actor: str = "human") -> None:
    """Recompute ancestors after a status write; childless rows keep manual status."""
    check_kind(kind)
    if kind == "task":
        t = store.get_task(obj_id)
        if t is None:
            return
        heal(store, "milestone", t.milestone_id, actor)
        s = store.get_milestone(t.milestone_id)
        if s is not None:
            heal(store, "plan", s.plan_id, actor)
    elif kind == "milestone":
        heal(store, "milestone", obj_id, actor)
        s = store.get_milestone(obj_id)
        if s is not None:
            heal(store, "plan", s.plan_id, actor)
    elif kind == "plan":
        heal(store, "plan", obj_id, actor)


def set_status(store: Store, kind: str, obj_id: int, status: Status, actor: str = "human") -> bool:
    """Move a row, heal the subtree state, and log the transition."""
    check_kind(kind)
    ok = store.set_status_raw(kind, obj_id, status)
    if ok:
        store.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        heal_parents(store, kind, obj_id, actor)
    return ok


def _norm_path(path: str) -> str:
    """Absolute normalized path for repo comparisons."""
    try:
        return str(Path(path).expanduser().resolve())
    except OSError:
        return str(Path(path).expanduser().absolute())


def _repo_for_task(store: Store, task_id: int, repo_path: str = "") -> dict:
    """Effective repo link for a task, honoring an explicit path."""
    repos = store.effective_repos("task", task_id)
    if repo_path:
        want = _norm_path(repo_path)
        for repo in repos:
            if repo.get("repo_path") == want:
                return repo
        return {"repo_path": want, "repo_remote": ""}
    for repo in repos:
        if repo.get("branch"):
            return repo
    if repos:
        return repos[0]
    backend, root = detect_backend(".")
    if backend is not None and root is not None:
        return {"repo_path": _norm_path(str(root)), "repo_remote": ""}
    raise ValueError("task has no linked repo; run link-repo first")


def _ensure_task_repo_links(store: Store, task_id: int, actor: str) -> None:
    """Copy inherited repos to explicit task links before recording a branch."""
    if store.list_repos("task", task_id):
        return
    for repo in store.effective_repos("task", task_id):
        store.add_repo_link(
            "task",
            task_id,
            repo.get("repo_path", ""),
            repo.get("repo_remote", ""),
            actor=actor,
        )


def start_task(
    store: Store,
    task_id: int,
    repo_path: str = "",
    branch: str = "",
    actor: str = "human",
) -> dict:
    """Start a task: record an existing branch and set doing. Never writes to git."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    chosen = _repo_for_task(store, task_id, repo_path)
    backend, root = detect_backend(chosen["repo_path"])
    if backend is None or root is None:
        raise ValueError("no VCS backend available (not a git repo)")

    current = backend.branch(root)
    name = branch.strip() or (current or "")
    if not name:
        raise ValueError("cannot start a task on a detached HEAD; check out a branch first")
    if not backend.branch_exists(root, name):
        raise ValueError(
            f"branch {name!r} does not exist; create it with your VCS tool, then run task start"
        )
    base = backend.merge_base(root, "HEAD", name) or backend.head(root) or ""
    _ensure_task_repo_links(store, task_id, actor)
    resolved_root = _norm_path(str(root))
    target = next(
        (repo for repo in store.list_repos("task", task_id) if repo["repo_path"] == resolved_root),
        None,
    )
    remote = target.get("repo_remote", "") if target else chosen.get("repo_remote", "")
    store.add_repo_link(
        "task",
        task_id,
        resolved_root,
        str(remote or ""),
        branch=name,
        base_sha=base,
        actor=actor,
    )
    set_status(store, "task", task_id, Status.DOING, actor=actor)
    return {
        "task": task_id,
        "repo_path": resolved_root,
        "branch": name,
        "base_sha": base,
    }


def _finish_target(store: Store, task_id: int, repo_path: str) -> dict:
    """Repo link for finishing a task, honoring an explicit checkout."""
    if repo_path:
        want = _norm_path(repo_path)
        for repo in store.list_repos("task", task_id):
            if repo["repo_path"] == want:
                return repo
        raise ValueError("repo is not linked to this task")
    for repo in store.list_repos("task", task_id):
        if repo.get("branch"):
            return repo
    repos = store.effective_repos("task", task_id)
    if len(repos) == 1:
        return repos[0]
    raise ValueError("task has no started branch; run task start first")


def _link_commits(
    store: Store,
    task_id: int,
    backend: VCSBackend,
    root: str,
    base: str,
    actor: str,
) -> int:
    """Link new commits in base..HEAD; return the count added."""
    existing = {link.sha for link in store.list_links("task", task_id)}
    linked = 0
    for commit in backend.log(root, f"{base}..HEAD"):
        if commit.sha in existing:
            continue
        store.link_commit(
            "task",
            task_id,
            commit.sha,
            subject=commit.subject,
            author=commit.author,
            timestamp=commit.timestamp,
            repo_root=commit.repo_root,
            actor=actor,
        )
        existing.add(commit.sha)
        linked += 1
    return linked


def finish_task(
    store: Store,
    task_id: int,
    repo_path: str = "",
    actor: str = "human",
) -> dict:
    """Link commits since the recorded base; move done only when the tree is clean."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    target = _finish_target(store, task_id, repo_path)
    branch = str(target.get("branch", "") or "")
    base = str(target.get("base_sha", "") or "")
    if not branch or not base:
        raise ValueError("task has no branch base; run task start first")
    backend, root = detect_backend(str(target.get("repo_path", "")))
    if backend is None or root is None:
        raise ValueError("no VCS backend available (not a git repo)")
    current = backend.branch(root)
    if current != branch:
        raise ValueError(f"expected branch {branch!r}, found {current or 'detached HEAD'}")
    status = backend.status(root)
    linked = _link_commits(store, task_id, backend, str(root), base, actor)
    done = False
    if not status.dirty:
        set_status(store, "task", task_id, Status.DONE, actor=actor)
        done = True
    return {
        "task": task_id,
        "repo_path": _norm_path(str(root)),
        "branch": branch,
        "base_sha": base,
        "linked": linked,
        "dirty": status.dirty,
        "done": done,
    }


def _trailer_refs(message: str) -> list[tuple[str, int]]:
    """Explicit Lazyplan trailer refs in one commit message."""
    found: set[tuple[str, int]] = set()
    for line in message.splitlines():
        match = _LAZYPLAN_TRAILER.match(line.strip())
        if not match:
            continue
        for token in re.split(r"[,\s]+", match.group(1)):
            ref = _LAZYPLAN_REF.match(token.strip())
            if ref:
                found.add((_KIND_BY_LETTER[ref.group(1).lower()], int(ref.group(2))))
    return sorted(found, key=lambda item: (item[0], item[1]))


def _branch_ref(branch: str) -> tuple[str, int] | None:
    """Plan/milestone/task ref encoded in a branch name."""
    match = _LAZYPLAN_BRANCH.match(branch)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def _branch_scan(
    store: Store,
    backend: VCSBackend,
    root: str,
    branch: str,
    limit: int,
) -> tuple[tuple[str, int] | None, set[str] | None]:
    """Branch ref plus the SHAs it owns (base..HEAD), when a base is recorded."""
    branch_ref = _branch_ref(branch)
    if branch_ref is None:
        return None, None
    ref_kind, ref_id = branch_ref
    base = ""
    for repo in store.list_repos(ref_kind, ref_id):
        if repo["repo_path"] == _norm_path(root) and repo.get("branch") == branch:
            base = str(repo.get("base_sha", "") or "")
            break
    if not base:
        return branch_ref, None
    return branch_ref, {commit.sha for commit in backend.log(root, f"{base}..HEAD", limit=limit)}


def _scan_wanted(ref_kind: str, ref_id: int, kind: str, obj_id: int) -> bool:
    """Whether a ref survives the optional kind/id filter."""
    if not kind:
        return True
    return ref_kind == kind and (not obj_id or ref_id == obj_id)


def _scan_ref_action(
    store: Store,
    commit: CommitInfo,
    ref_kind: str,
    ref_id: int,
    dry_run: bool,
    actor: str,
) -> str:
    """Link one ref or report why it was not written."""
    already = any(link.sha == commit.sha for link in store.list_links(ref_kind, ref_id))
    if already:
        return "already"
    if dry_run:
        return "would-link"
    store.link_commit(
        ref_kind,
        ref_id,
        commit.sha,
        subject=commit.subject,
        author=commit.author,
        timestamp=commit.timestamp,
        repo_root=commit.repo_root,
        actor=actor,
    )
    return "linked"


def scan_commits(
    store: Store,
    repo_path: str = ".",
    since: str = "",
    limit: int = 50,
    dry_run: bool = False,
    kind: str = "",
    obj_id: int = 0,
    actor: str = "human",
) -> list[dict]:
    """Link commits whose trailers or branch name name a plan/milestone/task."""
    backend, root = detect_backend(repo_path)
    if backend is None or root is None:
        raise ValueError("no VCS backend available (not a git repo)")
    if kind:
        check_kind(kind)
    branch_ref, branch_shas = _branch_scan(
        store, backend, str(root), backend.branch(root) or "", limit
    )
    matches: list[dict] = []
    for commit in backend.log(root, limit=limit, since=since):
        refs = set(_trailer_refs(f"{commit.subject}\n{commit.body}"))
        if branch_ref is not None and (branch_shas is None or commit.sha in branch_shas):
            refs.add(branch_ref)
        for ref_kind, ref_id in sorted(refs, key=lambda item: (item[0], item[1])):
            if not _scan_wanted(ref_kind, ref_id, kind, obj_id):
                continue
            if store.get_parent(ref_kind, ref_id) is None:
                continue
            action = _scan_ref_action(store, commit, ref_kind, ref_id, dry_run, actor)
            matches.append(
                {
                    "sha": commit.sha,
                    "subject": commit.subject,
                    "kind": ref_kind,
                    "id": ref_id,
                    "ref": f"{_LETTER_BY_KIND[ref_kind]}{ref_id}",
                    "action": action,
                }
            )
    return matches


def _task_capture_block(
    store: Store,
    task_id: int,
    backend: VCSBackend,
    root: str,
    sha: str,
) -> tuple[bool, str]:
    """Branch and history checks for auto-capturing a task's HEAD."""
    target = next(
        (repo for repo in store.list_repos("task", task_id) if repo.get("branch")),
        None,
    )
    if target is None:
        return False, ""
    if _norm_path(root) != target["repo_path"]:
        return True, "HEAD is in a different checkout than the task branch"
    branch = backend.branch(root)
    if branch != target["branch"]:
        return True, f"expected branch {target['branch']!r}, on {branch or 'detached HEAD'}"
    base = str(target.get("base_sha", "") or "")
    if base and backend.merge_base(root, base, sha) != base:
        return True, "HEAD is not on the task branch history"
    return False, ""


def _capture_block(
    store: Store,
    kind: str,
    obj_id: int,
    backend: VCSBackend,
    root: str,
    status: RepoStatus,
    sha: str,
) -> tuple[bool, str]:
    """Why HEAD should not be auto-linked; (False, "") means proceed."""
    if status.dirty:
        return True, "working tree is dirty"
    if any(link.sha == sha for link in store.list_links(kind, obj_id)):
        return True, ""
    others = [
        link
        for link in store.links_for_sha(sha)
        if not (link.parent_kind == kind and link.parent_id == obj_id)
    ]
    if others:
        other = others[0]
        return True, f"HEAD is already linked to {other.parent_kind} #{other.parent_id}"
    if kind == "task":
        return _task_capture_block(store, obj_id, backend, root, sha)
    return False, ""


def auto_capture_head(
    store: Store,
    kind: str,
    obj_id: int,
    cwd: str = ".",
    actor: str = "human",
) -> str | None:
    """Link HEAD on a done move when it is safe; return a reason when skipped."""
    backend, root = detect_backend(cwd)
    if backend is None or root is None:
        return None
    status = backend.status(root)
    sha = status.head or backend.head(root)
    if not sha:
        return None
    stop, reason = _capture_block(store, kind, obj_id, backend, str(root), status, sha)
    if stop:
        return reason or None
    info = backend.show(root, sha)
    if info is None:
        return None
    store.link_commit(
        kind,
        obj_id,
        info.sha,
        subject=info.subject,
        author=info.author,
        timestamp=info.timestamp,
        repo_root=info.repo_root,
        actor=actor,
    )
    return None


def _repo_targets(
    store: Store,
    kind: str = "",
    obj_id: int = 0,
    repo_path: str = "",
    cwd: str = ".",
) -> list[dict]:
    """Checkouts to inspect: one path, a row's effective repos, or cwd."""
    if repo_path:
        return [{"repo_path": _norm_path(repo_path), "repo_remote": ""}]
    if kind or obj_id:
        if not (kind and obj_id):
            raise ValueError("--kind and --id go together")
        check_kind(kind)
        return store.effective_repos(kind, obj_id)
    backend, root = detect_backend(cwd)
    if backend is None or root is None:
        raise ValueError("no VCS backend available (not a git repo)")
    return [{"repo_path": _norm_path(str(root)), "repo_remote": ""}]


def repo_statuses(
    store: Store,
    kind: str = "",
    obj_id: int = 0,
    repo_path: str = "",
    cwd: str = ".",
) -> list[dict]:
    """Branch and tracking state for one row's checkouts or one path."""
    targets = _repo_targets(store, kind, obj_id, repo_path, cwd)
    entries: list[dict] = []
    for target in targets:
        path = str(target.get("repo_path", "") or "")
        entry = {
            "repo_path": path,
            "repo_remote": str(target.get("repo_remote", "") or ""),
            "branch": "",
            "head": "",
            "dirty": False,
            "ahead": 0,
            "behind": 0,
            "upstream": "",
            "detached": False,
            "subject": "",
            "error": "",
        }
        backend, root = detect_backend(path)
        if backend is None or root is None:
            entry["error"] = "no VCS backend"
            entries.append(entry)
            continue
        status = backend.status(root)
        info = backend.show(root, status.head) if status.head else None
        entry.update(
            {
                "branch": status.branch,
                "head": status.head,
                "dirty": status.dirty,
                "ahead": status.ahead,
                "behind": status.behind,
                "upstream": status.upstream,
                "detached": status.detached,
                "subject": info.subject if info is not None else "",
            }
        )
        entries.append(entry)
    return entries


def forge_statuses(
    store: Store,
    kind: str = "",
    obj_id: int = 0,
    repo_path: str = "",
    cwd: str = ".",
    auth: AuthStatus | None = None,
) -> list[dict]:
    """GitHub identity and auth context for one row's checkouts or one path."""
    resolved = auth or resolve_auth()
    entries: list[dict] = []
    for target in _repo_targets(store, kind, obj_id, repo_path, cwd):
        path = str(target.get("repo_path", "") or "")
        entry = {
            "repo_path": path,
            "repo_remote": str(target.get("repo_remote", "") or ""),
            "provider": "",
            "host": "",
            "owner": "",
            "repo": "",
            "slug": "",
            "web_url": "",
            "auth_source": resolved.source,
            "auth_available": resolved.available,
            "cache": "none",
            "error": "",
        }
        backend, root = detect_backend(path)
        if backend is None or root is None:
            entry["error"] = "no VCS backend"
            entries.append(entry)
            continue
        remote = origin_url(backend, root) or str(entry["repo_remote"] or "")
        entry["repo_remote"] = remote
        if not remote:
            entry["error"] = "no origin remote"
            entries.append(entry)
            continue
        found = detect_forge(remote)
        if found is None:
            entry["error"] = "not a GitHub remote"
            entries.append(entry)
            continue
        forge, ref = found
        entry.update(
            {
                "provider": forge.name,
                "host": ref.host,
                "owner": ref.owner,
                "repo": ref.repo,
                "slug": ref.slug,
                "web_url": ref.web_url,
            }
        )
        entries.append(entry)
    return entries


def _pr_state(pr: dict) -> str:
    """Normalize a pull request to open/draft/merged/closed."""
    if pr.get("merged_at"):
        return "merged"
    state = str(pr.get("state", "") or "")
    if state == "open" and pr.get("draft"):
        return "draft"
    return state


def _checks_state(data: object) -> str:
    """Aggregate check runs to pass/fail/pending/none."""
    if not isinstance(data, dict):
        return "none"
    runs = data.get("check_runs", [])
    if not isinstance(runs, list) or not runs:
        return "none"
    statuses = [str(run.get("status", "") or "") for run in runs if isinstance(run, dict)]
    conclusions = [str(run.get("conclusion", "") or "") for run in runs if isinstance(run, dict)]
    if any(status != "completed" for status in statuses):
        return "pending"
    if any(
        conclusion in {"failure", "cancelled", "timed_out", "action_required"}
        for conclusion in conclusions
    ):
        return "fail"
    if all(conclusion in {"success", "neutral", "skipped"} for conclusion in conclusions):
        return "pass"
    return "none"


def _forge_target(path: str) -> tuple[Forge, RepoRef] | None:
    """Forge identity for one checkout path, or None when it cannot be resolved."""
    if not path:
        return None
    backend, root = detect_backend(path)
    if backend is None or root is None:
        return None
    remote = origin_url(backend, root)
    return detect_forge(remote) if remote else None


def _link_forge_target(link: object) -> tuple[Forge, RepoRef] | None:
    """Forge identity for one commit link, or None when it cannot be resolved."""
    return _forge_target(str(getattr(link, "repo_root", "") or ""))


def _pr_number(pr: object) -> int:
    """Positive PR/issue number from one API record, else 0."""
    if not isinstance(pr, dict):
        return 0
    try:
        return int(pr.get("number", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _pr_checks(
    gh: GitHubClient,
    ref: RepoRef,
    pr: dict,
    force: bool,
    stats: dict,
) -> tuple[str, bool]:
    """Fetch and aggregate check runs for one PR, recording errors."""
    head = pr.get("head") or {}
    head_sha = str(head.get("sha", "") or "") if isinstance(head, dict) else ""
    if not head_sha:
        return "none", False
    try:
        result = gh.checks(ref, head_sha, force=force)
    except GitHubError as exc:
        stats["errors"].append({"sha": head_sha, "error": str(exc)})
        return "none", False
    stats["checks"] += 1
    if result.stale:
        stats["stale"] += 1
    return _checks_state(result.data), result.stale


def _pr_reviews(
    gh: GitHubClient,
    ref: RepoRef,
    number: int,
    force: bool,
    stats: dict,
) -> tuple[str, bool]:
    """Fetch and summarize reviews for one PR, recording errors."""
    try:
        result = gh.reviews(ref, number, force=force)
    except GitHubError as exc:
        stats["errors"].append({"sha": f"PR #{number}", "error": str(exc)})
        return "none", False
    stats["reviews"] += 1
    if result.stale:
        stats["stale"] += 1
    data = result.data if isinstance(result.data, list) else []
    states = [
        str(review.get("state", "") or "").upper() for review in data if isinstance(review, dict)
    ]
    if "CHANGES_REQUESTED" in states:
        return "changes", result.stale
    if "APPROVED" in states:
        return "approved", result.stale
    return ("commented" if states else "none"), result.stale


def _store_pr(
    store: Store,
    gh: GitHubClient,
    forge: Forge,
    ref: RepoRef,
    pr: dict,
    parent_kind: str,
    parent_id: int,
    force: bool,
    stale: bool,
    stats: dict,
    actor: str,
) -> None:
    """Cache one PR on the row that owns its commit or branch."""
    number = _pr_number(pr)
    checks, checks_stale = _pr_checks(gh, ref, pr, force, stats)
    reviews, reviews_stale = _pr_reviews(gh, ref, number, force, stats)
    user = pr.get("user") or {}
    author = str(user.get("login", "") or "") if isinstance(user, dict) else ""
    base_raw = pr.get("base")
    head_raw = pr.get("head")
    base: dict = base_raw if isinstance(base_raw, dict) else {}
    head: dict = head_raw if isinstance(head_raw, dict) else {}
    store.link_forge(
        parent_kind,
        parent_id,
        number,
        provider=forge.name,
        kind="pull",
        url=str(pr.get("html_url", "") or pr.get("url", "") or ""),
        title=str(pr.get("title", "") or ""),
        state=_pr_state(pr),
        checks=checks,
        reviews=reviews,
        author=author,
        base_ref=str(base.get("ref", "") or ""),
        head_ref=str(head.get("ref", "") or ""),
        merged_at=str(pr.get("merged_at", "") or ""),
        merge_commit_sha=str(pr.get("merge_commit_sha", "") or ""),
        updated_at=int(time.time()),
        stale=stale or checks_stale or reviews_stale,
        payload=json.dumps(pr, separators=(",", ":"), sort_keys=True),
        actor=actor,
    )
    stats["linked"] += 1
    stats["prs"] += 1


def _store_pulls(
    store: Store,
    gh: GitHubClient,
    forge: Forge,
    ref: RepoRef,
    result: object,
    parent_kind: str,
    parent_id: int,
    force: bool,
    stats: dict,
    seen: set[tuple[str, str, int, str, int]],
    actor: str,
) -> None:
    """Cache every PR in one fetch result for a parent row, once per refresh."""
    stale = bool(getattr(result, "stale", False))
    pulls = getattr(result, "data", None)
    if not isinstance(pulls, list):
        return
    for pr in pulls:
        number = _pr_number(pr)
        if number <= 0:
            continue
        key = (ref.owner, ref.repo, number, parent_kind, parent_id)
        if key in seen:
            continue
        seen.add(key)
        _store_pr(
            store,
            gh,
            forge,
            ref,
            pr,
            parent_kind,
            parent_id,
            force,
            stale,
            stats,
            actor,
        )


def _tasks_in_scope(store: Store, kind: str, obj_id: int) -> list[Task]:
    """Tasks covered by a refresh: the row itself or its descendants."""
    if kind == "task":
        task = store.get_task(obj_id)
        return [task] if task is not None else []
    if kind == "milestone":
        return store.list_tasks(obj_id)
    tasks: list[Task] = []
    for milestone in store.list_milestones(obj_id):
        tasks.extend(store.list_tasks(milestone.id))
    return tasks


def refresh_forge(
    store: Store,
    kind: str,
    obj_id: int,
    client: GitHubClient | None = None,
    force: bool = True,
    actor: str = "human",
) -> dict:
    """Resolve commits and branches to PRs, then cache merge evidence."""
    check_kind(kind)
    gh = client or GitHubClient(store=store)
    stats: dict = {
        "commits": 0,
        "branches": 0,
        "merges": 0,
        "prs": 0,
        "linked": 0,
        "checks": 0,
        "reviews": 0,
        "skipped": 0,
        "stale": 0,
        "errors": [],
    }
    seen: set[tuple[str, str, int, str, int]] = set()
    for link in store.effective_links(kind, obj_id):
        found = _link_forge_target(link)
        if found is None:
            stats["skipped"] += 1
            continue
        forge, ref = found
        try:
            result = gh.pulls_for_commit(ref, link.sha, force=force)
        except GitHubError as exc:
            stats["errors"].append({"sha": link.sha, "error": str(exc)})
            continue
        stats["commits"] += 1
        if result.stale:
            stats["stale"] += 1
        _store_pulls(
            store,
            gh,
            forge,
            ref,
            result,
            link.parent_kind,
            link.parent_id,
            force,
            stats,
            seen,
            actor,
        )

    for task in _tasks_in_scope(store, kind, obj_id):
        for repo in store.effective_repos("task", task.id):
            branch = str(repo.get("branch", "") or "")
            if not branch:
                continue
            found = _forge_target(str(repo.get("repo_path", "") or ""))
            if found is None:
                stats["skipped"] += 1
                continue
            forge, ref = found
            try:
                result = gh.pulls_for_branch(ref, branch, force=force)
            except GitHubError as exc:
                stats["errors"].append({"branch": branch, "error": str(exc)})
                continue
            stats["branches"] += 1
            if result.stale:
                stats["stale"] += 1
            _store_pulls(
                store,
                gh,
                forge,
                ref,
                result,
                "task",
                task.id,
                force,
                stats,
                seen,
                actor,
            )

    for existing in store.effective_forge_links(kind, obj_id, kind="pull"):
        if not existing.merge_commit_sha:
            continue
        parsed = parse_pull_url(existing.url)
        if parsed is None:
            continue
        ref, _number = parsed
        found = detect_forge(ref.web_url)
        if found is None:
            continue
        forge, ref = found
        try:
            result = gh.pulls_for_merge(ref, existing.merge_commit_sha, force=force)
        except GitHubError as exc:
            stats["errors"].append({"merge_commit": existing.merge_commit_sha, "error": str(exc)})
            continue
        stats["merges"] += 1
        if result.stale:
            stats["stale"] += 1
        _store_pulls(
            store,
            gh,
            forge,
            ref,
            result,
            existing.parent_kind,
            existing.parent_id,
            force,
            stats,
            seen,
            actor,
        )
    return stats


def cycle_status(store: Store, kind: str, obj_id: int, actor: str = "human") -> Status | None:
    """Advance todo to doing to done to todo."""
    check_kind(kind)
    order = [Status.TODO, Status.DOING, Status.DONE]
    obj = store.get_parent(kind, obj_id)
    if obj is None:
        return None
    nxt = order[(order.index(obj.status) + 1) % len(order)]
    set_status(store, kind, obj_id, nxt, actor=actor)
    return nxt


def refresh_links(
    store: Store,
    kind: str,
    obj_id: int,
    actor: str = "human",
    cwd: str = ".",
) -> dict[str, int]:
    """Re-resolve cached commit links; mark missing commits stale."""
    check_kind(kind)
    now = int(time.time())
    links = store.effective_links(kind, obj_id)
    updated = 0
    stale = 0
    for link in links:
        info = None
        target = link.repo_root or cwd
        if not link.repo_root or Path(link.repo_root).is_dir():
            backend, root = detect_backend(target)
            if backend is not None and root is not None:
                info = backend.show(root, link.sha)
        if info is None:
            store.update_link(
                link.id,
                subject=link.subject,
                author=link.author,
                timestamp=link.timestamp,
                repo_root=link.repo_root,
                stale=True,
                checked_at=now,
                actor=actor,
            )
            stale += 1
            continue
        store.update_link(
            link.id,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            stale=False,
            checked_at=now,
            actor=actor,
        )
        updated += 1
    return {"checked": len(links), "updated": updated, "stale": stale}


def reconcile(store: Store, actor: str = "human") -> list[dict]:
    """Recompute every parent from its children; childless rows untouched."""
    changes: list[dict] = []
    for p in store.list_plans():
        before_p = p.status
        for s in store.list_milestones(p.id):
            before = s.status
            heal(store, "milestone", s.id, actor)
            after = store.get_milestone(s.id)
            if after is not None and after.status != before:
                changes.append({"kind": "milestone", "id": s.id, "to": after.status.value})
        heal(store, "plan", p.id, actor)
        after_p = store.get_plan(p.id)
        if after_p is not None and after_p.status != before_p:
            changes.append({"kind": "plan", "id": p.id, "to": after_p.status.value})
    return changes


# -- archive (day-old done hides; computed from status history) ------------
def is_archived(store: Store, plan: Plan) -> bool:
    """Done longer than a day, with history to prove it. No proof: never hide."""
    if plan.status != Status.DONE:
        return False
    last = None
    for ts, detail in store.status_events("plan"):
        cleaned = detail.removesuffix(" (rollup)")
        if cleaned.startswith(f"plan #{plan.id} -> "):
            last = (ts, cleaned[len(f"plan #{plan.id} -> ") :])
            break
    if last is None:
        return False
    ts, target = last
    return target == Status.DONE.value and (time.time() - ts) > ARCHIVE_AFTER_SECS


DEFAULT_PLAN_LIMIT = 5


# -- tree (shared list query, composed here) -------------------------------------------------
def plan_activity(store: Store) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    with store._connect() as conn:
        mrows = conn.execute("SELECT id, plan_id FROM milestones").fetchall()
        trows = conn.execute("SELECT id, milestone_id FROM tasks").fetchall()
        crows = conn.execute("SELECT id, parent_kind, parent_id FROM criteria").fetchall()
        events = conn.execute("SELECT ts, kind, detail FROM events").fetchall()
    mplan: dict[int, int] = {r["id"]: r["plan_id"] for r in mrows}
    tms: dict[int, int] = {r["id"]: r["milestone_id"] for r in trows}
    crit: dict[int, tuple[str, int]] = {r["id"]: (r["parent_kind"], r["parent_id"]) for r in crows}

    def resolve(kind: str, detail: str) -> int | None:
        m = re.match(r"([PMT])#(\d+)", detail)
        if m:
            letter, oid = m.group(1), int(m.group(2))
            if letter == "P":
                return oid
            if letter == "M":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"(plan|milestone|task) #(\d+)", detail)
        if m:
            kind, oid = m.group(1), int(m.group(2))
            if kind == "plan":
                return oid
            if kind == "milestone":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"criteria #(\d+)", detail)
        if m:
            found = crit.get(int(m.group(1)))
            if found is None:
                return None
            ckind, pid = found
            if ckind == "plan":
                return pid
            if ckind == "milestone":
                return mplan.get(pid)
            chained = tms.get(pid)
            return mplan.get(chained) if chained is not None else None
        return None

    out: dict[int, float] = {}
    for e in events:
        pid = resolve(e["kind"], e["detail"] or "")
        if pid is not None and e["ts"] > out.get(pid, 0.0):
            out[pid] = e["ts"]
    return out


def _filtered_milestones(
    store: Store,
    plan_id: int,
    status: Status | None,
) -> list[tuple[Milestone, list[Task]]]:
    """Milestone/task pairs of one plan honoring the status filter."""
    milestones = []
    for s in store.list_milestones(plan_id):
        tasks = store.list_tasks(s.id)
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
            if s.status != status and not tasks:
                continue
        milestones.append((s, tasks))
    return milestones


def _repo_match(want: str, repos: list[dict]) -> bool:
    """True when a repo filter matches any effective repo (path or remote)."""
    from pathlib import Path

    needle = (want or "").strip()
    if not needle:
        return True
    try:
        norm = str(Path(needle).expanduser().resolve())
    except OSError:
        norm = str(Path(needle).expanduser().absolute())
    lowered = needle.lower()
    for r in repos:
        path = str(r.get("repo_path", "") or "")
        remote = str(r.get("repo_remote", "") or "")
        if path and (path == norm or path == needle):
            return True
        if remote and (remote == needle or lowered in remote.lower()):
            return True
        if needle in path:
            return True
    return False


def _plan_matches_repo(store: Store, plan_id: int, want: str) -> bool:
    """True when a plan or any descendant effectively links the wanted repo."""
    if _repo_match(want, store.effective_repos("plan", plan_id)):
        return True
    for s in store.list_milestones(plan_id):
        if _repo_match(want, store.effective_repos("milestone", s.id)):
            return True
        for t in store.list_tasks(s.id):
            if _repo_match(want, store.effective_repos("task", t.id)):
                return True
    return False


def _visible_plan(
    store: Store,
    p: Plan,
    milestones: list[tuple[Milestone, list[Task]]],
    status: Status | None,
    archived: str,
) -> bool:
    """Whether a plan survives status/archive filters."""
    arch = is_archived(store, p)
    if archived == "only" and not arch:
        return False
    if archived == "hide" and arch:
        return False
    if status is not None and p.status != status and not milestones:
        return False
    return True


def tree(
    store: Store,
    status: Status | None = None,
    plan_id: int | None = None,
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters.

    archived: "hide" (default views), "only" (--archived), "show" (--status all).
    Plans order most-recently-active first (id fallback); limit caps the
    plan count (None = all). An explicit plan_id bypasses the cap.
    repo: only plans (or descendants) effectively linked to this repo.
    milestone_id: only this milestone (and its tasks) inside each plan.
    """
    if archived not in ("hide", "only", "show"):
        raise ValueError("archived must be hide|only|show")
    out = []
    for p in store.list_plans():
        if plan_id is not None and p.id != plan_id:
            continue
        if repo and not _plan_matches_repo(store, p.id, repo):
            continue
        milestones = _filtered_milestones(store, p.id, status)
        if milestone_id is not None:
            milestones = [(s, tasks) for s, tasks in milestones if s.id == milestone_id]
        if _visible_plan(store, p, milestones, status, archived):
            out.append((p, milestones))
    if plan_id is None and milestone_id is None:
        activity = plan_activity(store)
        out.sort(key=lambda e: (activity.get(e[0].id, 0.0), e[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out


# -- export / import (portability) ------------------------------------------
def export_all(store: Store) -> dict:
    """Full dump: plans (with criteria + links + repos) holding milestones and tasks."""
    plans = []
    for p in store.list_plans():
        milestones = []
        for s in store.list_milestones(p.id):
            tasks = []
            for t in store.list_tasks(s.id):
                tasks.append(
                    {
                        "task": _ser(vars(t)),
                        "criteria": [vars(c) for c in store.list_criteria("task", t.id)],
                        "links": [vars(c) for c in store.list_links("task", t.id)],
                        "forge_links": [vars(c) for c in store.list_forge_links("task", t.id)],
                        "repos": store.list_repos("task", t.id),
                    }
                )
            milestones.append(
                {
                    "milestone": _ser(vars(s)),
                    "criteria": [vars(c) for c in store.list_criteria("milestone", s.id)],
                    "links": [vars(c) for c in store.list_links("milestone", s.id)],
                    "forge_links": [vars(c) for c in store.list_forge_links("milestone", s.id)],
                    "repos": store.list_repos("milestone", s.id),
                    "tasks": tasks,
                }
            )
        plans.append(
            {
                "plan": _ser(vars(p)),
                "criteria": [vars(c) for c in store.list_criteria("plan", p.id)],
                "links": [vars(c) for c in store.list_links("plan", p.id)],
                "forge_links": [vars(c) for c in store.list_forge_links("plan", p.id)],
                "repos": store.list_repos("plan", p.id),
                "milestones": milestones,
            }
        )
    return {"lazyplan": 1, "plans": plans}


def export_plan(store: Store, plan_id: int) -> dict | None:
    """Single-plan entry in export_all() shape (or None when missing)."""
    plans: list[dict] = export_all(store)["plans"]
    for entry in plans:
        plan: dict = entry["plan"]
        if plan["id"] == plan_id:
            return entry
    return None


def import_all(store: Store, data: dict, actor: str = "human") -> dict[str, int]:
    """Load an export_all() dump. Returns counts.

    Template fill is skipped on import: the dump carries final values.
    """
    if not isinstance(data, dict) or data.get("lazyplan") != 1:
        raise ValueError("not a lazyplan export (missing lazyplan: 1)")
    counts = {
        "plans": 0,
        "milestones": 0,
        "tasks": 0,
        "criteria": 0,
        "links": 0,
        "repos": 0,
        "forge_links": 0,
    }

    def _apply_status(kind: str, obj_id: int, status: str) -> None:
        if status and status != Status.TODO.value:
            set_status(store, kind, obj_id, Status(status), actor=actor)

    def _import_criteria(kind: str, obj_id: int, items: list) -> None:
        for c in items:
            nc = store.add_criteria(kind, obj_id, c.get("text", ""), actor=actor)
            if c.get("done"):
                store.set_criteria(nc.id, True, actor=actor)
            counts["criteria"] += 1

    def _import_links(kind: str, obj_id: int, items: list) -> None:
        for c in items:
            sha = str(c.get("sha", "") or "").strip()
            if not sha:
                continue
            try:
                store.link_commit(
                    kind,
                    obj_id,
                    sha,
                    subject=str(c.get("subject", "") or ""),
                    author=str(c.get("author", "") or ""),
                    timestamp=int(c.get("timestamp", 0) or 0),
                    repo_root=str(c.get("repo_root", "") or ""),
                    actor=actor,
                )
            except ValueError:
                continue
            counts["links"] += 1

    def _import_repos(kind: str, obj_id: int, items: list) -> None:
        for r in items:
            path = str(r.get("repo_path", "") or "").strip()
            if not path:
                continue
            try:
                store.add_repo_link(
                    kind,
                    obj_id,
                    path,
                    repo_remote=str(r.get("repo_remote", "") or ""),
                    branch=str(r.get("branch", "") or ""),
                    base_sha=str(r.get("base_sha", "") or ""),
                    actor=actor,
                )
            except (ValueError, KeyError):
                continue
            counts["repos"] = counts.get("repos", 0) + 1

    def _import_forge_links(kind: str, obj_id: int, items: list) -> None:
        for item in items:
            number = int(item.get("number", 0) or 0)
            if number <= 0:
                continue
            try:
                store.link_forge(
                    kind,
                    obj_id,
                    number,
                    provider=str(item.get("provider", "") or "github"),
                    kind=str(item.get("kind", "") or "pull"),
                    url=str(item.get("url", "") or ""),
                    title=str(item.get("title", "") or ""),
                    state=str(item.get("state", "") or ""),
                    checks=str(item.get("checks", "") or ""),
                    reviews=str(item.get("reviews", "") or ""),
                    author=str(item.get("author", "") or ""),
                    base_ref=str(item.get("base_ref", "") or ""),
                    head_ref=str(item.get("head_ref", "") or ""),
                    merged_at=str(item.get("merged_at", "") or ""),
                    merge_commit_sha=str(item.get("merge_commit_sha", "") or ""),
                    updated_at=int(item.get("updated_at", 0) or 0),
                    stale=bool(item.get("stale", False)),
                    payload=str(item.get("payload", "") or ""),
                    actor=actor,
                )
            except (ValueError, KeyError):
                continue
            counts["forge_links"] += 1

    for entry in data.get("plans", []):
        p = entry["plan"]
        np = store.add_plan(
            p.get("name", p.get("title", "imported")),
            p.get("description", ""),
            goal=p.get("goal", ""),
            actor=actor,
        )
        _apply_status("plan", np.id, p.get("status", ""))
        counts["plans"] += 1
        _import_criteria("plan", np.id, entry.get("criteria", []))
        _import_links("plan", np.id, entry.get("links", []))
        _import_forge_links("plan", np.id, entry.get("forge_links", []))
        _import_repos("plan", np.id, entry.get("repos", []))
        for sentry in entry.get("milestones", []):
            sp = sentry["milestone"]
            ns = store.add_milestone(
                np.id,
                sp.get("title", ""),
                sp.get("description", ""),
                actor=actor,
            )
            _apply_status("milestone", ns.id, sp.get("status", ""))
            counts["milestones"] += 1
            _import_criteria("milestone", ns.id, sentry.get("criteria", []))
            _import_links("milestone", ns.id, sentry.get("links", []))
            _import_forge_links("milestone", ns.id, sentry.get("forge_links", []))
            _import_repos("milestone", ns.id, sentry.get("repos", []))
            for tentry in sentry.get("tasks", []):
                tp = tentry["task"]
                nt = store.add_task(
                    ns.id,
                    tp.get("title", ""),
                    description=tp.get("description", ""),
                    actor=actor,
                )
                _apply_status("task", nt.id, tp.get("status", ""))
                counts["tasks"] += 1
                _import_criteria("task", nt.id, tentry.get("criteria", []))
                _import_links("task", nt.id, tentry.get("links", []))
                _import_forge_links("task", nt.id, tentry.get("forge_links", []))
                _import_repos("task", nt.id, tentry.get("repos", []))
        # Milestones landed after the plan's own status: recompute it.
        heal(store, "plan", np.id, actor)
    return counts
