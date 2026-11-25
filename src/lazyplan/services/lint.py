"""Plan-quality lint: findings the trace graph and task text can prove.

Read-only and stdlib only. Lint is advisory; the CLI turns findings into a
strict exit code only when asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.entities import Milestone, Plan, Task
from ..core.policies.coordination import patterns_overlap
from ..core.ports.insights import InsightsPort
from . import plan_detail

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


def _open_on_done(store: InsightsPort, kind: str, obj_id: int) -> list[Finding]:
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


def _milestone_findings(milestone: Milestone) -> list[Finding]:
    """Resume-contract gaps in one milestone description."""
    issues = plan_detail.milestone_issues(milestone.description)
    if not issues:
        return []
    return [
        Finding(
            "incomplete-milestone-brief",
            "warn",
            f"milestone #{milestone.id} resume contract: {plan_detail.describe(issues)}",
            "milestone",
            milestone.id,
        )
    ]


def _task_findings(store: InsightsPort, task: Task) -> list[Finding]:
    """Rules that depend only on one task's description and status."""
    findings: list[Finding] = []
    task_id = task.id
    issues = plan_detail.task_issues(task.description)
    if issues:
        findings.append(
            Finding(
                "incomplete-task-brief",
                "warn",
                f"task #{task_id} resume contract: {plan_detail.describe(issues)}",
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


Lane = tuple[Milestone, list[Task]]


def _lane_findings(store: InsightsPort, plan: Plan) -> list[Finding]:
    """Parallel-plan rules: cap, lanes, waves, integrator, overlap, and roles."""
    if plan.dispatch_mode != "parallel":
        return []
    milestones = store.list_milestones(plan.id)
    lanes: list[Lane] = [(milestone, store.list_tasks(milestone.id)) for milestone in milestones]
    regular = [lane for lane in lanes if lane[0].agent_role != "integrator"]
    integrators = [lane for lane in lanes if lane[0].agent_role == "integrator"]
    findings = _shape_findings(plan, lanes)
    findings.extend(_integrator_findings(plan, regular, integrators))
    findings.extend(_wave_overlap_findings(store, lanes))
    findings.extend(_qa_coverage_findings(lanes, regular))
    return findings


def _shape_findings(plan: Plan, lanes: list[Lane]) -> list[Finding]:
    """Cap, lane count, and empty-lane rules."""
    findings: list[Finding] = []
    if plan.max_agents < 2:
        findings.append(
            Finding(
                "parallel-cap",
                "error",
                f"parallel plan #{plan.id} needs max_agents >= 2",
                "plan",
                plan.id,
            )
        )
    if len(lanes) < 2:
        findings.append(
            Finding(
                "parallel-lanes",
                "error",
                f"parallel plan #{plan.id} needs at least two lanes",
                "plan",
                plan.id,
            )
        )
    for milestone, tasks in lanes:
        if not tasks:
            findings.append(
                Finding(
                    "lane-without-tasks",
                    "error",
                    f"lane M{milestone.id} has no tasks",
                    "milestone",
                    milestone.id,
                )
            )
    return findings


def _integrator_findings(plan: Plan, regular: list[Lane], integrators: list[Lane]) -> list[Finding]:
    """Integrator presence and wave-order rules."""
    findings: list[Finding] = []
    if len(regular) > 1 and not integrators:
        findings.append(
            Finding(
                "missing-integrator",
                "error",
                f"parallel plan #{plan.id} with {len(regular)} lanes needs an integrator lane",
                "plan",
                plan.id,
            )
        )
    last_regular = max((milestone.lane_group for milestone, _ in regular), default=0)
    for milestone, _ in integrators:
        if milestone.lane_group <= last_regular:
            findings.append(
                Finding(
                    "integrator-order",
                    "error",
                    f"integrator lane M{milestone.id} must run after wave {last_regular}",
                    "milestone",
                    milestone.id,
                )
            )
    return findings


def _wave_overlap_findings(store: InsightsPort, lanes: list[Lane]) -> list[Finding]:
    """Touch-point collisions between two lanes that share a wave."""
    waves: dict[int, list[Lane]] = {}
    for milestone, tasks in lanes:
        waves.setdefault(milestone.lane_group, []).append((milestone, tasks))
    findings: list[Finding] = []
    for group, entries in sorted(waves.items()):
        for left in range(len(entries)):
            for right in range(left + 1, len(entries)):
                findings.extend(_overlap_findings(store, group, entries[left], entries[right]))
    return findings


def _qa_coverage_findings(lanes: list[Lane], regular: list[Lane]) -> list[Finding]:
    """Every non-integrator lane carries a qa task when the plan has one."""
    qa_in_plan = any(task.role == "qa" for _, tasks in lanes for task in tasks)
    if not qa_in_plan:
        return []
    findings: list[Finding] = []
    for milestone, tasks in regular:
        if not any(task.role == "qa" for task in tasks):
            findings.append(
                Finding(
                    "lane-missing-qa",
                    "error",
                    f"lane M{milestone.id} has no qa task while other lanes do",
                    "milestone",
                    milestone.id,
                )
            )
    return findings


def _overlap_findings(
    store: InsightsPort,
    group: int,
    left: tuple[Milestone, list[Task]],
    right: tuple[Milestone, list[Task]],
) -> list[Finding]:
    """Touch-point collisions between two lanes that share a wave."""
    findings: list[Finding] = []
    for left_task in left[1]:
        left_patterns = store.list_touchpoints(left_task.id)
        if not left_patterns:
            continue
        for right_task in right[1]:
            right_patterns = store.list_touchpoints(right_task.id)
            matched = _matched_patterns(left_patterns, right_patterns)
            if not matched:
                continue
            findings.append(
                Finding(
                    "lane-touchpoint-overlap",
                    "error",
                    f"tasks #{left_task.id} and #{right_task.id} share wave {group}: "
                    f"{', '.join(matched)}",
                    "task",
                    left_task.id,
                )
            )
    return findings


def _matched_patterns(left: list[str], right: list[str]) -> list[str]:
    """Patterns from *left* that overlap *right*, tolerating bad patterns."""
    matched: set[str] = set()
    for pattern in left:
        for candidate in right:
            try:
                overlap = patterns_overlap(pattern, candidate)
            except ValueError:
                overlap = False
            if overlap:
                matched.add(pattern)
    return sorted(matched)


def lint_plan(store: InsightsPort, plan_id: int) -> list[Finding] | None:
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
    latest = store.latest_revision(plan_id)
    if latest is not None and latest.enforced:
        drift = store.plan_drift(plan_id)
        if drift:
            findings.append(
                Finding(
                    "enforced-drift",
                    "error",
                    f"enforced plan has {drift} scope changes since r{latest.revision};"
                    " run plan diff",
                    "plan",
                    plan_id,
                )
            )
            missing = [
                change
                for change in store.list_plan_changes(plan_id, after_id=latest.change_mark)
                if not change.reason
            ]
            if missing:
                findings.append(
                    Finding(
                        "enforced-drift-no-reason",
                        "error",
                        f"{len(missing)} changes since r{latest.revision} have no reason",
                        "plan",
                        plan_id,
                    )
                )
    if plan.status.value == "done":
        findings.extend(_open_on_done(store, "plan", plan_id))
    findings.extend(_lane_findings(store, plan))
    for milestone in store.list_milestones(plan_id):
        findings.extend(_milestone_findings(milestone))
        if milestone.status.value == "done":
            findings.extend(_open_on_done(store, "milestone", milestone.id))
        for task in store.list_tasks(milestone.id):
            findings.extend(_task_findings(store, task))
    return findings
