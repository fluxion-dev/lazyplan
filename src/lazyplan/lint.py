"""Plan-quality lint: findings the trace graph and task text can prove.

Read-only and stdlib only. Lint is advisory; the CLI turns findings into a
strict exit code only when asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Task
from .store import Store

_PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    """One lint finding."""

    rule: str
    severity: str  # "error" | "warn"
    message: str
    kind: str
    obj_id: int

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "kind": self.kind,
            "id": self.obj_id,
        }


def _open_on_done(store: Store, kind: str, obj_id: int) -> list[Finding]:
    """Findings for a done row that still has open acceptance criteria."""
    if not store.open_criteria(kind, obj_id):
        return []
    return [
        Finding(
            "done-with-open-criteria",
            "error",
            f"{kind} #{obj_id} is done with open acceptance criteria",
            kind,
            obj_id,
        )
    ]


def _task_findings(store: Store, task: Task) -> list[Finding]:
    """Rules that depend only on one task's description and status."""
    findings: list[Finding] = []
    desc = task.description.lower()
    task_id = task.id
    if "commit" not in desc:
        findings.append(
            Finding(
                "missing-commit-slice",
                "warn",
                f"task #{task_id} has no commit slice in its description",
                "task",
                task_id,
            )
        )
    if "verif" not in desc:
        findings.append(
            Finding(
                "missing-verification",
                "warn",
                f"task #{task_id} has no verification in its description",
                "task",
                task_id,
            )
        )
    if _PLACEHOLDER.search(task.description):
        findings.append(
            Finding(
                "placeholder-text",
                "warn",
                f"task #{task_id} contains TODO/TBD/FIXME",
                "task",
                task_id,
            )
        )
    if task.status.value == "done":
        findings.extend(_open_on_done(store, "task", task_id))
    return findings


def lint_plan(store: Store, plan_id: int) -> list[Finding] | None:
    """Lint one plan; None when the plan does not exist."""
    plan = store.get_plan(plan_id)
    if plan is None:
        return None
    findings: list[Finding] = []
    for criterion in store.list_criteria("plan", plan_id):
        if not store.criterion_tasks(criterion.id):
            findings.append(
                Finding(
                    "uncovered-criterion",
                    "error",
                    f"criterion #{criterion.id} has no proving task",
                    "criterion",
                    criterion.id,
                )
            )
    if plan.status.value == "done":
        findings.extend(_open_on_done(store, "plan", plan_id))
    for milestone in store.list_milestones(plan_id):
        if milestone.status.value == "done":
            findings.extend(_open_on_done(store, "milestone", milestone.id))
        for task in store.list_tasks(milestone.id):
            findings.extend(_task_findings(store, task))
    return findings
