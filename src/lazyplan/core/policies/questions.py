"""Plan question rules: text, state, and the open subset."""

from __future__ import annotations

from collections.abc import Sequence

from ..entities import PlanQuestion
from ..kinds import QUESTION_STATUSES


def validate_text(text: str) -> str:
    """Trimmed question text; empty is rejected."""
    body = text.strip()
    if not body:
        raise ValueError("question text must not be empty")
    return body


def validate_status(status: str) -> str:
    """open or resolved."""
    if status not in QUESTION_STATUSES:
        raise ValueError(f"status must be {'|'.join(QUESTION_STATUSES)}")
    return status


def open_questions(rows: Sequence[PlanQuestion]) -> list[PlanQuestion]:
    """Only the unresolved questions, in creation order."""
    return [row for row in rows if row.status == "open"]


def open_count(rows: Sequence[PlanQuestion]) -> int:
    """How many questions still block readiness."""
    return sum(1 for row in rows if row.status == "open")
