"""Trace acceptance criteria to proving tasks, commits, and pull requests.

Read-only and stdlib only. The CLI renders these structures as text,
porcelain, or JSON; no network calls happen here.
"""

from __future__ import annotations

from .models import Criterion, Task
from .store import Store, _ser


def _task_entry(store: Store, task: Task) -> dict:
    """One proving task with its effective commits and PRs."""
    return {
        "task": _ser(vars(task)),
        "commits": [vars(link) for link in store.effective_links("task", task.id)],
        "forge_links": [vars(link) for link in store.effective_forge_links("task", task.id)],
    }


def _criterion_entry(store: Store, criterion: Criterion) -> dict:
    """One criterion with every proving task."""
    return {
        "criterion": vars(criterion),
        "tasks": [_task_entry(store, task) for task in store.criterion_tasks(criterion.id)],
    }


def trace_criterion(store: Store, criterion_id: int) -> dict | None:
    """Trace one criterion to its tasks, commits, and PRs."""
    criterion = store.get_criterion(criterion_id)
    if criterion is None:
        return None
    entry = _criterion_entry(store, criterion)
    return {"criterion": entry["criterion"], "tasks": entry["tasks"]}


def trace_plan(store: Store, plan_id: int) -> dict | None:
    """Trace every plan-level criterion to its tasks, commits, and PRs."""
    plan = store.get_plan(plan_id)
    if plan is None:
        return None
    return {
        "plan": _ser(vars(plan)),
        "criteria": [
            _criterion_entry(store, criterion) for criterion in store.list_criteria("plan", plan_id)
        ],
    }
