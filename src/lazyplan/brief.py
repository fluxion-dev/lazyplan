"""Session brief: the active plan, the next update, and loose commits.

Read-only and cheap enough for a session-start hook. It never creates a
database and never moves a row.
"""

from __future__ import annotations

from pathlib import Path

from . import audit
from .models import Plan, Status, Task
from .store import Store

_MAX_PLANS = 3
_MAX_LOOSE = 5
_MAX_GAPS = 5


def _active_plans(store: Store, plan_id: int | None) -> list[Plan]:
    if plan_id is not None:
        plan = store.get_plan(plan_id)
        return [plan] if plan is not None else []
    plans = store.list_plans()
    doing = [plan for plan in plans if plan.status == Status.DOING]
    if doing:
        return doing[:_MAX_PLANS]
    todo = [plan for plan in plans if plan.status == Status.TODO]
    return todo[:1]


def _tasks(store: Store, plan: Plan) -> list[Task]:
    out: list[Task] = []
    for milestone in store.list_milestones(plan.id):
        out.extend(store.list_tasks(milestone.id))
    return out


def _plan_brief(
    store: Store,
    plan: Plan,
    commits: list[audit.Commit] | None,
    cwd: str | Path,
) -> dict:
    tasks = _tasks(store, plan)
    doing = [task for task in tasks if task.status == Status.DOING]
    next_task = next((task for task in tasks if task.status == Status.TODO), None)
    criteria = [
        {"kind": "plan", "id": plan.id, "text": item.text}
        for item in store.open_criteria("plan", plan.id)
    ]
    for task in doing:
        criteria.extend(
            {"kind": "task", "id": task.id, "text": item.text}
            for item in store.open_criteria("task", task.id)
        )
    since = audit.plan_start(store, plan.id) or 0.0
    if commits is None:
        loose = audit.unlinked_commits(store, [plan.id], since, cwd)
    else:
        linked = audit.linked_shas(store, [plan.id])
        loose = [commit for commit in commits if commit.sha not in linked]
        loose.sort(key=lambda commit: commit.timestamp, reverse=True)
    return {
        "id": plan.id,
        "title": plan.name,
        "status": plan.status.value,
        "doing": [{"id": task.id, "title": task.title} for task in doing],
        "next": ({"id": next_task.id, "title": next_task.title} if next_task is not None else None),
        "criteria": criteria[:_MAX_GAPS],
        "unlinked": [
            {"sha": commit.sha, "subject": commit.subject, "timestamp": commit.timestamp}
            for commit in loose[:_MAX_LOOSE]
        ],
    }


def build(
    store: Store,
    plan_id: int | None = None,
    commits: list[audit.Commit] | None = None,
    cwd: str | Path = ".",
) -> dict:
    """Assemble the brief payload from existing rows and commits."""
    plans = _active_plans(store, plan_id)
    return {
        "plans": [_plan_brief(store, plan, commits, cwd) for plan in plans],
        "active": len(plans),
    }


def lines(payload: dict) -> list[str]:
    """Plain, hook-safe rendering of one brief payload."""
    plans = payload.get("plans") or []
    if not plans:
        return ["no active plans"]
    out: list[str] = []
    for plan in plans:
        out.append(f"P{plan['id']} {plan['title']} ({plan['status']})")
        for task in plan["doing"]:
            out.append(f"  doing    T{task['id']} {task['title']}")
        if not plan["doing"]:
            out.append("  doing    none")
        next_task = plan["next"]
        out.append(
            f"  next     T{next_task['id']} {next_task['title']}"
            if next_task
            else "  next     none"
        )
        if plan["criteria"]:
            out.append(f"  gaps     {len(plan['criteria'])} open criteria")
        if plan["unlinked"]:
            out.append(f"  unlinked {len(plan['unlinked'])} commits")
            for commit in plan["unlinked"]:
                out.append(f"    {commit['sha'][:8]} {commit['subject'][:60]}")
        out.append("  update   lpui task move --id N --to doing|done after each commit")
    return out
