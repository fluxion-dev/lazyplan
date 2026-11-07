"""Plan question use cases."""

from __future__ import annotations

from ..core.entities import PlanQuestion
from ..core.ports.planning import PlanningPort


def add_question(port: PlanningPort, plan_id: int, text: str, actor: str = "human") -> PlanQuestion:
    """Add one open question to a plan."""
    return port.add_question(plan_id, text, actor=actor)


def list_questions(port: PlanningPort, plan_id: int, status: str = "open") -> list[PlanQuestion]:
    """Questions on one plan, filtered by state."""
    return port.list_questions(plan_id, status)


def resolve_question(
    port: PlanningPort, qid: int, note: str = "", actor: str = "human"
) -> PlanQuestion | None:
    """Resolve one question with an optional answer."""
    return port.resolve_question(qid, note=note, actor=actor)


def reopen_question(
    port: PlanningPort, qid: int, note: str = "", actor: str = "human"
) -> PlanQuestion | None:
    """Reopen one question and record why."""
    return port.reopen_question(qid, note=note, actor=actor)
