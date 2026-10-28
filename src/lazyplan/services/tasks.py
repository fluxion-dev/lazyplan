"""Tasks services."""

from __future__ import annotations

from ..models import Status
from ..store import Store
from ..vcs import VCSBackend, detect_backend
from .base import (
    GateError,
)
from .plans import set_status
from .vcs import _ensure_task_repo_links, _norm_path, _repo_for_task


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
    owners = store.branch_owners(
        resolved_root, name, remote=str(remote or ""), exclude_task=task_id
    )
    if owners:
        raise ValueError(
            f"branch {name!r} is already recorded on task #{owners[0].id}; "
            "use another branch or finish that task first"
        )
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
        info = backend.show(root, commit.sha) or commit
        store.link_commit(
            "task",
            task_id,
            info.sha,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            files=info.files,
            actor=actor,
        )
        existing.add(commit.sha)
        linked += 1
    return linked


def gate_state(store: Store, task_id: int) -> dict:
    """Cached PR/check gate state for one task."""
    return store.gate_state(task_id)


def _gate_failure(gate: dict, require_pr: bool, require_checks: bool) -> str:
    """Human gate failure, or empty when the gates pass."""
    if require_pr and gate["prs"] == 0:
        return "completion gate: no linked pull request"
    if require_checks and gate["checks"] != "pass":
        return f"completion gate: checks are {gate['checks']}"
    return ""


def finish_task(
    store: Store,
    task_id: int,
    repo_path: str = "",
    actor: str = "human",
    require_pr: bool = False,
    require_checks: bool = False,
    override: str = "",
) -> dict:
    """Link commits since the recorded base; move done only when the tree is clean."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    gate = gate_state(store, task_id)
    failure = _gate_failure(gate, require_pr, require_checks)
    if failure and not override:
        raise GateError(failure)
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
    if override and (require_pr or require_checks):
        store.add_note(
            "task",
            task_id,
            f"Gate override by {actor}: {override} (prs={gate['prs']}, checks={gate['checks']})",
            actor=actor,
        )
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
        "gate": gate,
    }
