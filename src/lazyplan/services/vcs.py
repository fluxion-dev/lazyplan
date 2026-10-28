"""Vcs services."""

from __future__ import annotations

import re
from pathlib import Path

from ..kinds import check_kind
from ..store import Store
from ..vcs import CommitInfo, RepoStatus, VCSBackend, detect_backend
from .base import (
    _KIND_BY_LETTER,
    _LAZYPLAN_BRANCH,
    _LAZYPLAN_REF,
    _LAZYPLAN_TRAILER,
    _LETTER_BY_KIND,
)


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
    files: tuple[str, ...] = (),
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
        files=files,
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
            info = backend.show(root, commit.sha) or commit
            action = _scan_ref_action(
                store, commit, ref_kind, ref_id, dry_run, actor, files=info.files
            )
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
        files=info.files,
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
