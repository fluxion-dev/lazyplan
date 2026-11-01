"""Compatibility shim; canonical home is ``lazyplan.services.planning``."""

from __future__ import annotations

from .planning import (
    DEFAULT_PLAN_LIMIT,
    _filtered_milestones,
    _is_archived,
    _plan_activity,
    _plan_matches_repo,
    _repo_match,
    _visible_plan,
    is_archived,
    plan_activity,
    tree,
)

__all__ = [
    "DEFAULT_PLAN_LIMIT",
    "_filtered_milestones",
    "_is_archived",
    "_plan_activity",
    "_plan_matches_repo",
    "_repo_match",
    "_visible_plan",
    "is_archived",
    "plan_activity",
    "tree",
]
