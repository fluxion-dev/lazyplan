"""Shared element vocabulary: single source of truth for kind names.

Every layer imports from here instead of repeating literals, so renames
and new kinds touch one file. Stdlib only.
"""

from __future__ import annotations

PLAN = "plan"
MILESTONE = "milestone"
TASK = "task"

#: All element kinds, in hierarchy order.
KINDS: tuple[str, str, str] = (PLAN, MILESTONE, TASK)

#: Row label letters, matching the design row grammar.
LABEL_LETTERS: dict[str, str] = {PLAN: "P", MILESTONE: "M", TASK: "T"}

#: Storage table per kind.
TABLES: dict[str, str] = {PLAN: "plans", MILESTONE: "milestones", TASK: "tasks"}

#: Shared validation messages (single wording for every layer).
KIND_ERROR = f"kind must be {'|'.join(KINDS)}"
PARENT_KIND_ERROR = f"parent_kind must be {'|'.join(KINDS)}"


def check_kind(kind: str) -> str:
    """Validate an element kind, naming the allowed values."""
    if kind not in KINDS:
        raise ValueError(KIND_ERROR)
    return kind


def check_parent_kind(parent_kind: str) -> str:
    """Validate a criteria/link parent kind, naming the allowed values."""
    if parent_kind not in KINDS:
        raise ValueError(PARENT_KIND_ERROR)
    return parent_kind


def table_for(kind: str) -> str:
    """Storage table for a kind (validates first)."""
    return TABLES[check_kind(kind)]
