"""Session brief: the active plan, the next update, and loose commits.

Read-only and cheap enough for a session-start hook. It never creates a
database and never moves a row.
"""

from __future__ import annotations

from pathlib import Path

from lazyplan.services import audit

from ..core.entities import Plan, Status, Task
from ..core.ports.insights import InsightsPort
from ..core.serialization import approval_payload

_MAX_PLANS = 3
_MAX_LOOSE = 5
_MAX_GAPS = 5
_MAX_PLAN_NOTES = 5


def _active_plans(store: InsightsPort, plan_id: int | None) -> list[Plan]:
    if plan_id is not None:
        plan = store.get_plan(plan_id)
        return [plan] if plan is not None else []
    plans = store.list_plans()
    doing = [plan for plan in plans if plan.status == Status.DOING]
    if doing:
        return doing[:_MAX_PLANS]
    todo = [plan for plan in plans if plan.status == Status.TODO]
    return todo[:1]


def _tasks(store: InsightsPort, plan: Plan) -> list[Task]:
    out: list[Task] = []
    for milestone in store.list_milestones(plan.id):
        out.extend(store.list_tasks(milestone.id))
    return out


def _doing(store: InsightsPort, task: Task) -> dict:
    """Doing-task brief entry with its claim when one exists."""
    entry: dict = {"id": task.id, "title": task.title}
    claim = store.get_claim(task.id)
    if claim is not None:
        entry["claim"] = vars(claim)
    notes = store.list_notes("task", task.id)
    if notes:
        entry["notes"] = [vars(n) for n in notes]
    comments = store.list_comments("task", task.id)
    if comments:
        entry["comments"] = [vars(c) for c in comments]
    gate = store.gate_state(task.id)
    if gate["prs"]:
        entry["gate"] = gate
    return entry


def _criteria(store: InsightsPort, plan: Plan, doing: list[Task]) -> list[dict]:
    """Open plan criteria plus the doing tasks' criteria."""
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


def _loose_commits(
    store: InsightsPort,
    plan: Plan,
    commits: list[audit.Commit] | None,
    cwd: str | Path,
) -> list[audit.Commit]:
    """Commits in the plan window that are not linked to it."""
    since = audit.plan_start(store, plan.id) or 0.0
    if commits is None:
        return audit.unlinked_commits(store, [plan.id], since, cwd)
    linked = audit.linked_shas(store, [plan.id])
    loose = [commit for commit in commits if commit.sha not in linked]
    loose.sort(key=lambda commit: commit.timestamp, reverse=True)
    return loose


def _approval(store: InsightsPort, plan: Plan) -> dict:
    """Latest revision and live drift for one plan."""
    latest = store.latest_revision(plan.id)
    return approval_payload(latest, store.plan_drift(plan.id) if latest is not None else 0)


def _plan_brief(
    store: InsightsPort,
    plan: Plan,
    commits: list[audit.Commit] | None,
    cwd: str | Path,
) -> dict:
    tasks = _tasks(store, plan)
    doing = [task for task in tasks if task.status == Status.DOING]
    next_task = next(
        (task for task in tasks if task.status == Status.TODO and not task.blocked), None
    )
    loose = _loose_commits(store, plan, commits, cwd)
    payload = {
        "id": plan.id,
        "title": plan.name,
        "status": plan.status.value,
        "doing": [_doing(store, task) for task in doing],
        "next": ({"id": next_task.id, "title": next_task.title} if next_task is not None else None),
        "criteria": _criteria(store, plan, doing)[:_MAX_GAPS],
        "unlinked": [
            {"sha": commit.sha, "subject": commit.subject, "timestamp": commit.timestamp}
            for commit in loose[:_MAX_LOOSE]
        ],
    }
    payload["approval"] = _approval(store, plan)
    payload["questions"] = [vars(q) for q in store.list_questions(plan.id)]
    notes = store.list_notes("plan", plan.id)[:_MAX_PLAN_NOTES]
    if notes:
        payload["notes"] = [vars(n) for n in notes]
    comments = store.list_comments("plan", plan.id)
    if comments:
        payload["comments"] = [vars(c) for c in comments]
    return payload


def build(
    store: InsightsPort,
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


def _approval_line(plan: dict) -> str | None:
    """One brief line for the plan's approval state, or None."""
    approval = plan.get("approval") or {}
    revision = int(approval.get("revision", 0) or 0)
    if not revision:
        return None
    flags = " enforced" if approval.get("enforced") else ""
    drift = int(approval.get("drift", 0) or 0)
    if drift:
        return f"  drift    {drift} changes since r{revision}{flags}"
    return f"  approval r{revision}{flags} in sync"


def _question_lines(plan: dict) -> list[str]:
    """Open questions with their ids, capped for scanning."""
    questions = plan.get("questions") or []
    if not questions:
        return []
    lines = [f"  questions {len(questions)} open"]
    lines.extend(
        f"    Q{question['id']} {str(question['text'])[:60]}" for question in questions[:3]
    )
    return lines


def lines(payload: dict) -> list[str]:
    """Plain, hook-safe rendering of one brief payload."""
    plans = payload.get("plans") or []
    if not plans:
        return ["no active plans"]
    out: list[str] = []
    for plan in plans:
        out.append(f"P{plan['id']} {plan['title']} ({plan['status']})")
        approval = _approval_line(plan)
        if approval is not None:
            out.append(approval)
        out.extend(_question_lines(plan))
        for note in plan.get("notes", []):
            out.append(f"  note     @{note['actor']}: {note['text']}")
        for comment in plan.get("comments", []):
            if not comment.get("resolved"):
                out.append(f"  comment  @{comment['actor']}: {comment['text']}")
        for task in plan["doing"]:
            claim = task.get("claim")
            suffix = f" @{claim['actor']}" if claim else ""
            out.append(f"  doing    T{task['id']} {task['title']}{suffix}")
            for note in task.get("notes", []):
                out.append(f"    note   @{note['actor']}: {note['text']}")
            for comment in task.get("comments", []):
                if not comment.get("resolved"):
                    out.append(f"    comment @{comment['actor']}: {comment['text']}")
            gate = task.get("gate")
            if gate:
                out.append(f"    gate     {gate['state']} · {gate['prs']} PRs")
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
