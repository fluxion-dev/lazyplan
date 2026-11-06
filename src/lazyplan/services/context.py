"""Budgeted context packet for a cold agent session.

The packet is a read-only slice of the active plan: why and what, the doing
task, the next few tasks, open criteria, decisions, commits, comments, and
claims. It never writes and never creates a database. Truncation is
deterministic: low-priority sections drop until the compact JSON fits.
"""

from __future__ import annotations

import json

from ..core.entities import Plan, Status, Task
from ..core.ports.insights import InsightsPort

DEFAULT_CONTEXT_CHARS = 4000
MIN_CONTEXT_CHARS = 120


def _active_plan(store: InsightsPort, plan_id: int | None) -> Plan | None:
    if plan_id is not None:
        return store.get_plan(plan_id)
    plans = store.list_plans()
    doing = [plan for plan in plans if plan.status == Status.DOING]
    if doing:
        return doing[0]
    todo = [plan for plan in plans if plan.status == Status.TODO]
    return todo[0] if todo else None


def _tasks(store: InsightsPort, plan: Plan) -> list[Task]:
    out: list[Task] = []
    for milestone in store.list_milestones(plan.id):
        out.extend(store.list_tasks(milestone.id))
    return out


def _claims(store: InsightsPort, plan: Plan) -> dict[int, dict]:
    return {int(item["task_id"]): item for item in store.list_claims(plan_id=plan.id)}


def _open_criteria(store: InsightsPort, plan: Plan, doing: list[Task]) -> list[dict]:
    out = [
        {"kind": "plan", "id": plan.id, "text": item.text}
        for item in store.open_criteria("plan", plan.id)
    ]
    for task in doing:
        out.extend(
            {"kind": "task", "id": task.id, "text": item.text}
            for item in store.open_criteria("task", task.id)
        )
    return out


def _notes(store: InsightsPort, plan: Plan, doing: list[Task]) -> list[dict]:
    out: list[dict] = []
    for note in store.list_notes("plan", plan.id)[:5]:
        out.append(
            {
                "id": note.id,
                "parent_kind": "plan",
                "parent_id": plan.id,
                "actor": note.actor,
                "text": note.text,
                "ts": note.ts,
            }
        )
    for task in doing:
        for note in store.list_notes("task", task.id)[:3]:
            out.append(
                {
                    "id": note.id,
                    "parent_kind": "task",
                    "parent_id": task.id,
                    "actor": note.actor,
                    "text": note.text,
                    "ts": note.ts,
                }
            )
    return out[-5:]


def _comments(store: InsightsPort, plan: Plan, doing: list[Task]) -> list[dict]:
    out: list[dict] = []
    for comment in store.list_comments("plan", plan.id):
        if not comment.resolved:
            out.append(
                {
                    "id": comment.id,
                    "parent_kind": "plan",
                    "parent_id": plan.id,
                    "actor": comment.actor,
                    "text": comment.text,
                    "ts": comment.ts,
                    "resolved": False,
                }
            )
    for task in doing:
        for comment in store.list_comments("task", task.id):
            if not comment.resolved:
                out.append(
                    {
                        "id": comment.id,
                        "parent_kind": "task",
                        "parent_id": task.id,
                        "actor": comment.actor,
                        "text": comment.text,
                        "ts": comment.ts,
                        "resolved": False,
                    }
                )
    return out[-5:]


def _commits(store: InsightsPort, plan: Plan) -> list[dict]:
    links = sorted(
        store.effective_links("plan", plan.id),
        key=lambda link: link.timestamp,
        reverse=True,
    )
    return [
        {
            "sha": link.sha,
            "short": link.sha[:8],
            "subject": link.subject,
            "timestamp": link.timestamp,
        }
        for link in links[:5]
    ]


def _packet(store: InsightsPort, plan: Plan) -> dict:
    tasks = _tasks(store, plan)
    claims = _claims(store, plan)
    doing = [task for task in tasks if task.status == Status.DOING][:3]
    next_tasks = [
        task
        for task in tasks
        if task.status == Status.TODO and not task.blocked and task.id not in claims
    ][:3]
    return {
        "id": plan.id,
        "title": plan.name,
        "status": plan.status.value,
        "why": plan.goal,
        "what": plan.description,
        "doing": [
            {
                "id": task.id,
                "title": task.title,
                "claim": claims.get(task.id),
            }
            for task in doing
        ],
        "next": [{"id": task.id, "title": task.title} for task in next_tasks],
        "criteria": _open_criteria(store, plan, doing),
        "notes": _notes(store, plan, doing),
        "comments": _comments(store, plan, doing),
        "commits": _commits(store, plan),
        "claims": list(claims.values()),
    }


def _encoded(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _fits(payload: dict, max_chars: int) -> bool:
    return len(_encoded(payload)) <= max_chars


def _cap(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"


def _trim(payload: dict, max_chars: int) -> dict:
    if _fits(payload, max_chars):
        payload["truncated"] = False
        return payload
    payload["truncated"] = True
    plans = payload["plans"]
    for plan in plans:
        for key in ("comments", "notes", "commits", "claims"):
            if _fits(payload, max_chars):
                return payload
            plan[key] = []
        if not _fits(payload, max_chars):
            plan["next"] = plan["next"][:1]
        if not _fits(payload, max_chars):
            plan["criteria"] = plan["criteria"][:3]
        if not _fits(payload, max_chars):
            plan["doing"] = [
                {"id": task["id"], "title": _cap(str(task["title"]), 80), "claim": task["claim"]}
                for task in plan["doing"]
            ]
        if not _fits(payload, max_chars):
            plan["why"] = ""
            plan["what"] = ""
    if not _fits(payload, max_chars):
        payload["plans"] = [
            {
                "id": plan["id"],
                "title": _cap(str(plan["title"]), 40),
                "status": plan["status"],
            }
            for plan in plans
        ]
    return payload


def build(
    store: InsightsPort,
    plan_id: int | None = None,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
) -> dict:
    """Build one budgeted, read-only context packet."""
    if max_chars < MIN_CONTEXT_CHARS:
        raise ValueError(f"max_chars must be at least {MIN_CONTEXT_CHARS}")
    plan = _active_plan(store, plan_id)
    payload = {
        "active": 1 if plan is not None else 0,
        "plans": [_packet(store, plan)] if plan is not None else [],
        "truncated": False,
    }
    return _trim(payload, max_chars)


def lines(payload: dict) -> list[str]:
    """Plain text rendering for hooks and the CLI."""
    plans = payload.get("plans") or []
    if not plans:
        return ["no active plans"]
    out: list[str] = []
    for plan in plans:
        out.append(f"P{plan['id']} {plan['title']} ({plan['status']})")
        if plan.get("why"):
            out.append(f"  why      {plan['why']}")
        if plan.get("doing"):
            for task in plan["doing"]:
                claim = task.get("claim")
                suffix = f" @{claim['actor']}" if claim else ""
                out.append(f"  doing    T{task['id']} {task['title']}{suffix}")
        else:
            out.append("  doing    none")
        for task in plan.get("next") or []:
            out.append(f"  next     T{task['id']} {task['title']}")
        if plan.get("criteria"):
            out.append(f"  gaps     {len(plan['criteria'])} open criteria")
        for note in plan.get("notes") or []:
            out.append(f"  note     @{note['actor']}: {note['text']}")
        for comment in plan.get("comments") or []:
            out.append(f"  comment  @{comment['actor']}: {comment['text']}")
        if plan.get("commits"):
            out.append(f"  commits  {len(plan['commits'])} recent")
        if payload.get("truncated"):
            out.append("  truncated to budget")
    return out
