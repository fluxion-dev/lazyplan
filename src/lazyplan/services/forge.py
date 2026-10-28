"""Forge services."""

from __future__ import annotations

import json
import time

from ..forge import AuthStatus, Forge, RepoRef, detect_forge, parse_pull_url, resolve_auth
from ..github import GitHubClient, GitHubError
from ..kinds import check_kind
from ..models import Task
from ..store import Store
from ..vcs import detect_backend, origin_url
from .vcs import _repo_targets


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
