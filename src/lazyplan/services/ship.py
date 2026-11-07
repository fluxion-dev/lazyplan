"""Outcome ship note: why, what shipped, evidence, risks, and follow-ups."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Plan, Status
from ..core.policies.ship import render
from ..core.ports.insights import InsightsPort
from . import review


@dataclass(frozen=True)
class ShipNote:
    """One rendered ship note and the structured payload behind it."""

    plan_id: int
    markdown: str
    payload: dict


def _tasks(store: InsightsPort, plan_id: int) -> list:
    return [
        task
        for milestone in store.list_milestones(plan_id)
        for task in store.list_tasks(milestone.id)
    ]


def build(
    store: InsightsPort,
    plan_id: int,
    max_chars: int = 0,
    cwd: str | Path = ".",
) -> ShipNote | None:
    """Compose one ship note; None when the plan does not exist."""
    packet = review.build(store, plan_id, max_chars=0, cwd=cwd)
    if packet is None:
        return None
    plan = store.get_plan(plan_id)
    assert plan is not None
    base = packet.payload
    tasks = _tasks(store, plan_id)
    milestones = [
        {
            "id": milestone["id"],
            "title": milestone["title"],
            "status": milestone["status"],
            "done": sum(1 for task in milestone.get("tasks", []) if task.get("status") == "done"),
            "total": len(milestone.get("tasks", [])),
        }
        for milestone in base.get("milestones", [])
    ]
    criteria = base.get("criteria", [])
    payload = {
        "plan": {"id": plan.id, "name": plan.name, "status": plan.status.value},
        "why": plan.goal,
        "milestones": milestones,
        "tasks": {
            "done": sum(1 for task in tasks if task.status == Status.DONE),
            "total": len(tasks),
        },
        "done_tasks": [
            {"id": task.id, "title": task.title} for task in tasks if task.status == Status.DONE
        ],
        "open_tasks": [
            {"id": task.id, "title": task.title} for task in tasks if task.status != Status.DONE
        ],
        "criteria": {
            "total": len(criteria),
            "evidence": sum(1 for item in criteria if item.get("evidence") == "pass"),
        },
        "open_criteria": [item for item in criteria if not item.get("done")],
        "audit": base.get("audit", {}),
        "commits": base.get("commits", []),
        "prs": base.get("prs", []),
        "questions": [
            question for question in base.get("questions", []) if question.get("status") == "open"
        ],
        "blocked": [{"id": task.id, "title": task.title} for task in tasks if task.blocked],
        "stale": sum(1 for link in store.effective_links("plan", plan_id) if link.stale),
        "notes": base.get("notes", []),
    }
    return ShipNote(plan_id, render(payload, max_chars), payload)


def active_plan(store: InsightsPort) -> Plan | None:
    """First doing plan, else the first todo plan."""
    plans = store.list_plans()
    doing = [plan for plan in plans if plan.status.value == "doing"]
    if doing:
        return doing[0]
    todo = [plan for plan in plans if plan.status.value == "todo"]
    return todo[0] if todo else None
