"""Read-only verification for a registered plan worktree."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..infrastructure.repo import git_common_dir
from ..infrastructure.vcs import GitBackend


@dataclass(frozen=True)
class WorktreeVerification:
    """The outcome of checking one worktree against its linked checkout."""

    ok: bool
    reason: str = ""
    branch: str = ""
    head: str = ""
    dirty: bool = False


def _refuse(
    reason: str, branch: str = "", head: str = "", dirty: bool = False
) -> WorktreeVerification:
    return WorktreeVerification(False, reason=reason, branch=branch, head=head, dirty=dirty)


def verify_worktree(repo_path: str, worktree_path: str, branch: str) -> WorktreeVerification:
    """Check that *worktree_path* is this repo's checkout on *branch* and clean."""
    if os.path.normcase(os.path.abspath(repo_path)) == os.path.normcase(
        os.path.abspath(worktree_path)
    ):
        return _refuse("worktree path must differ from the linked checkout")

    repo_common = git_common_dir(repo_path)
    if not repo_common:
        return _refuse(f"linked checkout is not a git repository: {repo_path}")
    worktree_common = git_common_dir(worktree_path)
    if not worktree_common:
        return _refuse(f"worktree is not a git checkout: {worktree_path}")
    if os.path.normcase(repo_common) != os.path.normcase(worktree_common):
        return _refuse("worktree belongs to a different repository")

    status = GitBackend().status(worktree_path)
    if status.detached or not status.branch:
        return _refuse("worktree has a detached HEAD", head=status.head, dirty=status.dirty)
    if status.branch != branch:
        return _refuse(
            f"worktree is on branch {status.branch!r}, expected {branch!r}",
            branch=status.branch,
            head=status.head,
            dirty=status.dirty,
        )
    if status.dirty:
        return _refuse(
            "worktree has uncommitted changes",
            branch=status.branch,
            head=status.head,
            dirty=True,
        )
    return WorktreeVerification(True, branch=status.branch, head=status.head)
