"""Core element vocabulary: single source of truth for kind names.

Every layer imports from here instead of repeating literals, so renames
and new kinds touch one file. Stdlib only.
"""

from __future__ import annotations

PLAN = "plan"
MILESTONE = "milestone"
TASK = "task"
CRITERION = "criterion"

#: All element kinds, in hierarchy order.
KINDS: tuple[str, str, str] = (PLAN, MILESTONE, TASK)

#: Kinds that can appear in a scope change; criteria are scope too.
SCOPE_KINDS: tuple[str, str, str, str] = (PLAN, MILESTONE, TASK, CRITERION)

#: Plan-question states.
QUESTION_STATUSES: tuple[str, str] = ("open", "resolved")

#: Row label letters, matching the design row grammar.
LABEL_LETTERS: dict[str, str] = {PLAN: "P", MILESTONE: "M", TASK: "T"}

#: Storage table per kind.
TABLES: dict[str, str] = {PLAN: "plans", MILESTONE: "milestones", TASK: "tasks"}

#: Shared validation messages (single wording for every layer).
KIND_ERROR = f"kind must be {'|'.join(KINDS)}"
PARENT_KIND_ERROR = f"parent_kind must be {'|'.join(KINDS)}"


def _check(value: str, message: str) -> str:
    """One allowed-kind check with the caller's message."""
    if value not in KINDS:
        raise ValueError(message)
    return value


def check_kind(kind: str) -> str:
    """Validate an element kind, naming the allowed values."""
    return _check(kind, KIND_ERROR)


def check_parent_kind(parent_kind: str) -> str:
    """Validate a criteria/link parent kind, naming the allowed values."""
    return _check(parent_kind, PARENT_KIND_ERROR)


def table_for(kind: str) -> str:
    """Storage table for a kind (validates first)."""
    return TABLES[check_kind(kind)]
