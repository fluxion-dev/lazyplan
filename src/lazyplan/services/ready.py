"""Plan readiness: lint, plan-criterion coverage, and open questions."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.ports.insights import InsightsPort
from . import lint


@dataclass(frozen=True)
class ReadyCheck:
    """One readiness rule and its result."""

    id: str
    ok: bool
    detail: str
    findings: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ReadyResult:
    """All readiness checks for one plan."""

    plan_id: int
    checks: tuple[ReadyCheck, ...]

    @property
    def ready(self) -> bool:
        """True only when every check passes."""
        return all(check.ok for check in self.checks)


def check(port: InsightsPort, plan_id: int) -> ReadyResult | None:
    """Check one plan for readiness; None when the plan does not exist."""
    if port.get_plan(plan_id) is None:
        return None
    findings = lint.lint_plan(port, plan_id) or []
    lint_check = ReadyCheck(
        "lint",
        not findings,
        "clean" if not findings else f"{len(findings)} findings",
        tuple(finding.to_dict() for finding in findings),
    )
    criteria = port.list_criteria("plan", plan_id)
    uncovered = [criterion for criterion in criteria if not port.criterion_tasks(criterion.id)]
    coverage = ReadyCheck(
        "coverage",
        not uncovered,
        f"{len(criteria) - len(uncovered)}/{len(criteria)} plan criteria have a proving task",
        tuple({"id": criterion.id, "text": criterion.text} for criterion in uncovered),
    )
    questions = port.list_questions(plan_id)
    question_check = ReadyCheck(
        "questions",
        not questions,
        f"{len(questions)} open questions" if questions else "none open",
        tuple({"id": question.id, "text": question.text} for question in questions),
    )
    return ReadyResult(plan_id, (lint_check, coverage, question_check))
