"""Trace acceptance criteria to proving tasks, commits, and pull requests.

Read-only and stdlib only. The CLI renders these structures as text,
porcelain, or JSON; no network calls happen here.
"""

from __future__ import annotations

from ..core.entities import Criterion, Task
from ..core.policies.maintenance import is_archived_row
from ..core.ports.provenance import ProvenancePort
from ..core.serialization import to_payload


def _task_entry(store: ProvenancePort, task: Task) -> dict:
    """One proving task with its effective commits and PRs."""
    return {
        "task": to_payload(vars(task)),
        "issues": store.list_issue_links("task", task.id),
        "commits": [vars(link) for link in store.effective_links("task", task.id)],
        "forge_links": [vars(link) for link in store.effective_forge_links("task", task.id)],
    }


def _criterion_entry(store: ProvenancePort, criterion: Criterion) -> dict:
    """One criterion with every proving task."""
    return {
        "criterion": vars(criterion),
        "evidence": [vars(row) for row in store.list_evidence(criterion.id)],
        "tasks": [_task_entry(store, task) for task in store.criterion_tasks(criterion.id)],
    }


def _plan_id_for_criterion(store: ProvenancePort, criterion: Criterion) -> int | None:
    """Owning plan id for one criterion, or None when a parent is missing."""
    if criterion.parent_kind == "plan":
        return criterion.parent_id
    if criterion.parent_kind == "milestone":
        milestone = store.get_milestone(criterion.parent_id)
        return milestone.plan_id if milestone is not None else None
    task = store.get_task(criterion.parent_id)
    if task is None:
        return None
    milestone = store.get_milestone(task.milestone_id)
    return milestone.plan_id if milestone is not None else None


def _archived_plan(store: ProvenancePort, plan_id: int | None) -> bool:
    """True when a plan is hidden from reads by its archive stamp."""
    if plan_id is None:
        return False
    plan = store.get_plan(plan_id)
    return plan is not None and is_archived_row(plan)


def trace_criterion(store: ProvenancePort, criterion_id: int) -> dict | None:
    """Trace one criterion to its tasks, commits, and PRs."""
    criterion = store.get_criterion(criterion_id)
    if criterion is None:
        return None
    if _archived_plan(store, _plan_id_for_criterion(store, criterion)):
        return None
    entry = _criterion_entry(store, criterion)
    return {
        "criterion": entry["criterion"],
        "evidence": entry["evidence"],
        "tasks": entry["tasks"],
    }


def trace_plan(store: ProvenancePort, plan_id: int) -> dict | None:
    """Trace every plan-level criterion to its tasks, commits, and PRs."""
    plan = store.get_plan(plan_id)
    if plan is None or is_archived_row(plan):
        return None
    return {
        "plan": to_payload(vars(plan)),
        "criteria": [
            _criterion_entry(store, criterion) for criterion in store.list_criteria("plan", plan_id)
        ],
    }
