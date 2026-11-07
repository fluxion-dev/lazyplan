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


def _task_rows(tasks: list) -> tuple[list[dict], list[dict]]:
    """Done and open task summaries."""
    done = [{"id": task.id, "title": task.title} for task in tasks if task.status == Status.DONE]
    open_tasks = [
        {"id": task.id, "title": task.title} for task in tasks if task.status != Status.DONE
    ]
    return done, open_tasks


def _milestone_rows(base: dict) -> list[dict]:
    """Milestone done and total task counts."""
    return [
        {
            "id": milestone["id"],
            "title": milestone["title"],
            "status": milestone["status"],
            "done": sum(1 for task in milestone.get("tasks", []) if task.get("status") == "done"),
            "total": len(milestone.get("tasks", [])),
        }
        for milestone in base.get("milestones", [])
    ]


def _payload(plan: Plan, tasks: list, base: dict) -> dict:
    """Structured ship payload rolled up from the review packet."""
    done_tasks, open_tasks = _task_rows(tasks)
    criteria = base.get("criteria", [])
    return {
        "plan": {"id": plan.id, "name": plan.name, "status": plan.status.value},
        "why": plan.goal,
        "milestones": _milestone_rows(base),
        "tasks": {"done": len(done_tasks), "total": len(tasks)},
        "done_tasks": done_tasks,
        "open_tasks": open_tasks,
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
        "notes": base.get("notes", []),
    }


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
    payload = _payload(plan, _tasks(store, plan_id), packet.payload)
    payload["stale"] = sum(1 for link in store.effective_links("plan", plan_id) if link.stale)
    return ShipNote(plan_id, render(payload, max_chars), payload)
