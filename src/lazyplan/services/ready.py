"""Plan readiness: lint, plan-criterion coverage, and open questions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..core.policies.context import DEFAULT_CONTEXT_WINDOW, DEFAULT_TASK_CONTEXT_PERCENT
from ..core.policies.maintenance import is_archived_row
from ..core.policies.questions import open_count, open_questions
from ..core.ports.insights import InsightsPort
from . import lint, task_brief
from .worktrees import worktree_gate

_CONTEXT_EXTRA = "Claim the task, work in the lane checkout, link each commit, and finish the task."


@dataclass(frozen=True)
class ReadyCheck:
    """One readiness rule and its result."""

    id: str
    ok: bool
    detail: str
    findings: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        """JSON-safe check."""
        return {
            "id": self.id,
            "ok": self.ok,
            "detail": self.detail,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class ReadyResult:
    """All readiness checks for one plan."""

    plan_id: int
    checks: tuple[ReadyCheck, ...]

    @property
    def ready(self) -> bool:
        """True only when every check passes."""
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict:
        """JSON-safe result shared by the CLI and MCP."""
        return {
            "plan": self.plan_id,
            "ready": self.ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def check(
    port: InsightsPort,
    plan_id: int,
    *,
    context_windows: Mapping[str, int] | None = None,
    context_percent: int = DEFAULT_TASK_CONTEXT_PERCENT,
) -> ReadyResult | None:
    """Check one plan for readiness; None when the plan is missing or archived."""
    plan = port.get_plan(plan_id)
    if plan is None or is_archived_row(plan):
        return None
    findings = lint.lint_plan(port, plan_id) or []
    lint_check = ReadyCheck(
        "lint",
        not findings,
        "clean" if not findings else f"{len(findings)} findings",
        tuple(finding.to_dict() for finding in findings),
    )
    context_check = _context_check(
        port,
        plan_id,
        context_windows or {},
        context_percent,
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
    open_items = open_questions(questions)
    question_check = ReadyCheck(
        "questions",
        not open_items,
        f"{open_count(questions)} open questions" if open_items else "none open",
        tuple({"id": question.id, "text": question.text} for question in open_items),
    )
    blocker = worktree_gate(port, plan_id)
    repos = port.list_repos("plan", plan_id)
    if not plan.worktree_required:
        worktree_detail = "not required"
    elif blocker:
        worktree_detail = blocker
    else:
        worktree_detail = f"{len(repos)}/{len(repos)} registered"
    worktree_check = ReadyCheck("worktrees", not blocker, worktree_detail)
    return ReadyResult(
        plan_id,
        (lint_check, context_check, coverage, question_check, worktree_check),
    )


def _context_check(
    port: InsightsPort,
    plan_id: int,
    windows: Mapping[str, int],
    percent: int,
) -> ReadyCheck:
    """Every task's fresh brief must fit its role's context budget."""
    tasks = [
        task
        for milestone in port.list_milestones(plan_id)
        for task in port.list_tasks(milestone.id)
        if task.status.value != "done"
    ]
    findings: list[dict] = []
    for task in tasks:
        window = windows.get(task.role, DEFAULT_CONTEXT_WINDOW)
        brief = task_brief.build(port, task.id, window, percent, extra=_CONTEXT_EXTRA)
        if brief.fits:
            continue
        findings.append(
            {
                "id": task.id,
                "message": (
                    f"T{task.id} uses {brief.tokens:,} tokens of a {brief.budget:,} budget"
                    f" ({brief.percent}% of {window:,})"
                ),
                "task": task.title,
                "tokens": brief.tokens,
                "window": brief.window,
                "budget": brief.budget,
                "percent": brief.percent,
            }
        )
    total = len(tasks)
    detail = (
        f"{total - len(findings)}/{total} tasks fit the {percent}% context budget"
        if total
        else "no tasks"
    )
    return ReadyCheck("context", not findings, detail, tuple(findings))
