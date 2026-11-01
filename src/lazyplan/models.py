"""Compatibility shim; canonical home is ``lazyplan.core.entities``."""

from __future__ import annotations

from .core.entities import (
    CRITERION_PARENTS,
    Claim,
    Comment,
    Criterion,
    ForgeLink,
    Issue,
    Milestone,
    Note,
    Plan,
    Status,
    Task,
    VcsLink,
)
from .core.kinds import KINDS, PARENT_KIND_ERROR

__all__ = [
    "CRITERION_PARENTS",
    "KINDS",
    "PARENT_KIND_ERROR",
    "Claim",
    "Comment",
    "Criterion",
    "ForgeLink",
    "Issue",
    "Milestone",
    "Note",
    "Plan",
    "Status",
    "Task",
    "VcsLink",
]
