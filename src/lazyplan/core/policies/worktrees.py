"""Pure plan-worktree path and branch derivation.

A plan worktree is a sibling checkout of each linked repository, named
``<repo>--plan-<id>-<slug>`` on branch ``plan/<id>-<slug>``. The policy never
touches the filesystem: callers pass normalized absolute repo paths and may
inject an existence check for the collision refusal.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

_SLUG_WORD = re.compile(r"[a-z0-9]+")
_SLUG_MAX = 48
_FALLBACK = "plan"


class WorktreeCollision(ValueError):
    """A derived worktree path already exists; lazyplan never suffixes it."""


@dataclass(frozen=True)
class WorktreeTarget:
    """One derived checkout for a plan and linked repository."""

    repo_path: str
    worktree_path: str
    branch: str


def slugify(title: str) -> str:
    """Lowercase ASCII slug, bounded, with ``plan`` for an empty result."""
    words = _SLUG_WORD.findall(title.lower())
    slug = "-".join(words)[:_SLUG_MAX].strip("-")
    return slug or _FALLBACK


def derive_worktree(repo_path: str, plan_id: int, title: str) -> WorktreeTarget:
    """Derive the sibling path and branch for one repository."""
    if plan_id < 1:
        raise ValueError("plan id must be positive")
    repo = os.path.normpath(repo_path)
    parent, name = os.path.split(repo)
    if not name or not parent:
        raise ValueError(f"repo path must be an absolute checkout: {repo_path!r}")
    slug = slugify(title)
    worktree = os.path.join(parent, f"{name}--plan-{plan_id}-{slug}")
    return WorktreeTarget(
        repo_path=repo,
        worktree_path=worktree,
        branch=f"plan/{plan_id}-{slug}",
    )


def derive_worktrees(
    repo_paths: Iterable[str],
    plan_id: int,
    title: str,
    exists: Callable[[str], bool] | None = None,
) -> list[WorktreeTarget]:
    """Derive one target per unique repo; refuse a path that already exists."""
    targets: list[WorktreeTarget] = []
    seen: set[str] = set()
    for repo_path in repo_paths:
        target = derive_worktree(repo_path, plan_id, title)
        if target.repo_path in seen:
            continue
        seen.add(target.repo_path)
        if exists is not None and exists(target.worktree_path):
            raise WorktreeCollision(f"worktree path already exists: {target.worktree_path}")
        targets.append(target)
    return targets
