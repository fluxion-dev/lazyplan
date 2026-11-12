"""Read-only control-room payload: attention, plan health, sessions, and claims.

One bounded read assembles the rows the TUI shows without opening detail. It
never writes and never starts a git or network call.
"""

from __future__ import annotations

import time
from typing import Any

from ..core.entities import Plan, Task
from ..core.policies.coordination import patterns_overlap
from ..core.policies.maintenance import is_archived_row
from ..core.ports.needs_me import NeedsMePort
from ..core.serialization import approval_payload
from . import stats
from .sessions import session_state

ATTENTION_LIMIT = 20
PLAN_LIMIT = 25
SESSION_LIMIT = 8
CLAIM_LIMIT = 20
OVERLAP_LIMIT = 10
OVERLAP_CLAIM_LIMIT = 40

_REASON_PRIORITY = {
    "blocked": 0,
    "stale claim": 1,
    "aging doing": 2,
    "unclaimed doing": 3,
    "done with open criteria": 4,
    "failing checks": 5,
}


def _plans(port: NeedsMePort, plan_id: int | None) -> list[Plan]:
    if plan_id is None:
        return port.list_plans(archived="hide")
    plan = port.get_plan(plan_id)
    if plan is None or is_archived_row(plan):
        return []
    return [plan]


def _task_index(
    port: NeedsMePort, plan_ids: set[int]
) -> tuple[dict[int, int], dict[int, Task], dict[int, list[Task]]]:
    """Task to plan/milestone maps and per-plan task lists from bulk reads."""
    milestones = port.milestones_map()
    tasks = port.tasks_map()
    task_plan: dict[int, int] = {}
    task_by_id: dict[int, Task] = {}
    tasks_by_plan: dict[int, list[Task]] = {plan_id: [] for plan_id in plan_ids}
    for plan_id in plan_ids:
        for milestone in milestones.get(plan_id, []):
            for task in tasks.get(milestone.id, []):
                task_plan[task.id] = plan_id
                task_by_id[task.id] = task
                tasks_by_plan[plan_id].append(task)
    return task_plan, task_by_id, tasks_by_plan


def _attention_rows(
    port: NeedsMePort,
    task_plan: dict[int, int],
    task_by_id: dict[int, Task],
    tasks_by_plan: dict[int, list[Task]],
    active_task_ids: set[int],
    expired_task_ids: set[int],
    plan_names: dict[int, str],
    stale_after: float,
    stamp: float,
    *,
    claims_map: dict,
    forge: dict,
    open_criteria: set[int],
    task_rows: list[Task],
) -> list[dict[str, Any]]:
    """Task rows that need a human, with the reason for each."""
    reasons = stats.attention_reasons(
        port,
        stale_after=stale_after,
        now=stamp,
        tasks=task_rows,
        claims=claims_map,
        forge=forge,
        open_criteria=open_criteria,
    )
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for task_id, found in reasons.items():
        plan_id = task_plan.get(task_id)
        task = task_by_id.get(task_id)
        if plan_id is None or task is None:
            continue
        reasons_for_task = list(found)
        if (
            task.status.value == "doing"
            and task_id not in active_task_ids
            and task_id not in expired_task_ids
            and "unclaimed doing" not in reasons_for_task
        ):
            reasons_for_task.append("unclaimed doing")
        rows.append(_attention_row(task, plan_id, plan_names, reasons_for_task))
        seen.add(task_id)

    for plan_id, tasks in tasks_by_plan.items():
        for task in tasks:
            if (
                task.id in seen
                or task.status.value != "doing"
                or task.id in active_task_ids
                or task.id in expired_task_ids
            ):
                continue
            rows.append(_attention_row(task, plan_id, plan_names, ["unclaimed doing"]))

    rows.sort(key=lambda row: (_REASON_PRIORITY.get(row["reasons"][0], 99), row["task_id"]))
    return rows


def _attention_row(
    task: Task, plan_id: int, plan_names: dict[int, str], reasons: list[str]
) -> dict[str, Any]:
    """One compact attention row."""
    return {
        "task_id": task.id,
        "milestone_id": task.milestone_id,
        "plan_id": plan_id,
        "plan_title": plan_names.get(plan_id, ""),
        "title": task.title,
        "status": task.status.value,
        "blocked": task.blocked,
        "reasons": reasons,
    }


def _task_counts(tasks: list[Task]) -> dict[str, int]:
    counts = {"todo": 0, "doing": 0, "done": 0}
    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
    return counts


def _plan_health(
    plans: list[Plan],
    tasks_by_plan: dict[int, list[Task]],
    expired_task_ids: set[int],
    latest: dict,
    drift: dict,
    questions: dict,
    refs: dict,
    active_claims: list[dict],
) -> tuple[list[dict[str, Any]], set[int], int]:
    """Per-plan approval, questions, references, claims, and reasons."""
    rows: list[dict[str, Any]] = []
    needs_me: set[int] = set()
    open_questions = 0
    for plan in plans:
        plan_id = int(plan.id)
        plan_tasks = tasks_by_plan.get(plan_id, [])
        plan_questions = [
            question for question in questions.get(plan_id, []) if question.status == "open"
        ]
        plan_refs = refs.get(plan_id, [])
        plan_claims = [claim for claim in active_claims if int(claim["plan_id"]) == plan_id]
        approval = approval_payload(latest.get(plan_id), int(drift.get(plan_id, 0)))
        reasons: list[str] = []
        if int(approval.get("drift", 0)):
            reasons.append("drift")
        if plan_questions:
            reasons.append("open questions")
        if any(task.blocked for task in plan_tasks):
            reasons.append("blocked work")
        if any(task.id in expired_task_ids for task in plan_tasks):
            reasons.append("stale claim")
        if reasons:
            needs_me.add(plan_id)
        open_questions += len(plan_questions)
        rows.append(
            {
                "id": plan_id,
                "title": plan.name,
                "status": plan.status.value,
                "approval": approval,
                "question_count": len(plan_questions),
                "questions": [
                    {"id": question.id, "text": question.text} for question in plan_questions
                ],
                "reference_count": len(plan_refs),
                "claim_count": len(plan_claims),
                "task_counts": _task_counts(plan_tasks),
                "reasons": reasons,
            }
        )
    rows.sort(key=lambda row: (not row["reasons"], row["id"]))
    return rows, needs_me, open_questions


def _overlaps(
    claims: list[dict], touchpoints: dict[int, list[str]], limit: int
) -> list[dict[str, Any]]:
    """Pairs of active claims whose touch-points can cover the same path."""
    out: list[dict[str, Any]] = []
    for index, left in enumerate(claims):
        left_patterns = touchpoints.get(int(left["task_id"]), [])
        if not left_patterns:
            continue
        for right in claims[index + 1 :]:
            right_patterns = touchpoints.get(int(right["task_id"]), [])
            if not right_patterns:
                continue
            left_repo = str(left.get("repo_path") or "")
            right_repo = str(right.get("repo_path") or "")
            if left_repo and right_repo and left_repo != right_repo:
                continue
            matched = sorted(
                {
                    pattern
                    for pattern in left_patterns
                    for candidate in right_patterns
                    if patterns_overlap(pattern, candidate)
                }
                | {
                    candidate
                    for pattern in left_patterns
                    for candidate in right_patterns
                    if patterns_overlap(pattern, candidate)
                }
            )
            if not matched:
                continue
            out.append(
                {
                    "task_ids": sorted([int(left["task_id"]), int(right["task_id"])]),
                    "actors": [str(left.get("actor") or ""), str(right.get("actor") or "")],
                    "patterns": matched,
                }
            )
            if len(out) >= limit:
                return out
    return out


def _expired_ids(claims_map: dict, task_plan: dict[int, int], stamp: float) -> set[int]:
    return {
        task_id
        for task_id, claim in claims_map.items()
        if task_id in task_plan and claim.expired(stamp)
    }


def _active_claims(
    port: NeedsMePort, plan_id: int | None, plan_ids: set[int], stamp: float
) -> list[dict]:
    claims = port.list_claims(include_expired=False, now=stamp, plan_id=plan_id)
    if plan_id is None:
        return claims
    return [claim for claim in claims if int(claim["plan_id"]) in plan_ids]


def _session_rows(
    port: NeedsMePort,
    plan_id: int | None,
    plan_names: dict[int, str],
    max_sessions: int,
    stamp: float,
) -> list[dict[str, Any]]:
    sessions = port.list_sessions(open_only=True, plan_id=plan_id, limit=max_sessions)
    return [
        {
            "id": session.id,
            "actor": session.actor,
            "plan_id": session.plan_id,
            "plan_title": plan_names.get(int(session.plan_id or 0), ""),
            "branch": session.branch,
            "host": session.host,
            "phase": session.phase,
            "state": session_state(session, stamp),
            "started_at": session.started_at,
            "last_seen_at": session.last_activity(),
            "idle": round(session.idle_seconds(stamp), 1),
            "duration": round(session.duration(stamp), 1),
        }
        for session in sessions
    ]


def _claim_rows(active_claims: list[dict], max_claims: int, stamp: float) -> list[dict[str, Any]]:
    return [
        {
            "task_id": int(claim["task_id"]),
            "task_title": str(claim.get("task_title") or ""),
            "task_status": str(claim.get("task_status") or ""),
            "milestone_id": int(claim.get("milestone_id") or 0),
            "plan_id": int(claim.get("plan_id") or 0),
            "plan_title": str(claim.get("plan_title") or ""),
            "actor": str(claim.get("actor") or ""),
            "expires_at": float(claim.get("expires_at") or 0.0),
            "expires_in": max(0.0, float(claim.get("expires_at") or 0.0) - stamp),
            "worktree": str(claim.get("worktree") or ""),
            "repo_path": str(claim.get("repo_path") or ""),
        }
        for claim in active_claims[:max_claims]
    ]


def _needs_me_ids(
    task_plan: dict[int, int], attention_task_ids: set[int], plan_needs_me: set[int]
) -> set[int]:
    out = set(plan_needs_me)
    for task_id in attention_task_ids:
        plan_for_task = task_plan.get(task_id)
        if plan_for_task is not None:
            out.add(plan_for_task)
    return out


def _counts(
    plans: list[Plan],
    attention_all: list[dict],
    session_rows: list[dict],
    active_claims: list[dict],
    open_questions: int,
    health: list[dict],
    overlap_rows: list[dict],
) -> dict[str, int]:
    return {
        "plans": len(plans),
        "attention": len(attention_all),
        "sessions": len(session_rows),
        "claims": len(active_claims),
        "open_questions": open_questions,
        "drift": sum(1 for row in health if int(row["approval"].get("drift", 0))),
        "overlaps": len(overlap_rows),
    }


def build(
    port: NeedsMePort,
    *,
    now: float | None = None,
    stale_after: float = stats.ATTENTION_STALE_SECS,
    plan_id: int | None = None,
    max_attention: int = ATTENTION_LIMIT,
    max_plans: int = PLAN_LIMIT,
    max_sessions: int = SESSION_LIMIT,
    max_claims: int = CLAIM_LIMIT,
    max_overlaps: int = OVERLAP_LIMIT,
) -> dict[str, Any]:
    """Assemble the control-room payload from bulk reads."""
    stamp = time.time() if now is None else now
    plans = _plans(port, plan_id)
    plan_ids = {int(plan.id) for plan in plans}
    plan_names = {int(plan.id): str(plan.name) for plan in plans}

    task_plan, task_by_id, tasks_by_plan = _task_index(port, plan_ids)
    claims_map = port.claims_map()
    expired_task_ids = _expired_ids(claims_map, task_plan, stamp)
    active_claims = _active_claims(port, plan_id, plan_ids, stamp)
    active_task_ids = {int(claim["task_id"]) for claim in active_claims}
    task_rows = [task for tasks in tasks_by_plan.values() for task in tasks]

    attention_all = _attention_rows(
        port,
        task_plan,
        task_by_id,
        tasks_by_plan,
        active_task_ids,
        expired_task_ids,
        plan_names,
        stale_after,
        stamp,
        claims_map=claims_map,
        forge=port.forge_links_map(),
        open_criteria=port.open_task_criteria_ids(),
        task_rows=task_rows,
    )
    attention_task_ids = {int(row["task_id"]) for row in attention_all}

    health, plan_needs_me, open_questions = _plan_health(
        plans,
        tasks_by_plan,
        expired_task_ids,
        port.latest_revisions_map(),
        port.drift_counts(),
        port.questions_map(),
        port.refs_map(),
        active_claims,
    )
    needs_me_plan_ids = _needs_me_ids(task_plan, attention_task_ids, plan_needs_me)

    session_rows = _session_rows(port, plan_id, plan_names, max_sessions, stamp)
    claim_rows = _claim_rows(active_claims, max_claims, stamp)
    overlap_rows = _overlaps(
        active_claims[:OVERLAP_CLAIM_LIMIT], port.touchpoints_map(), max_overlaps
    )
    counts = _counts(
        plans,
        attention_all,
        session_rows,
        active_claims,
        open_questions,
        health,
        overlap_rows,
    )
    return {
        "generated_at": stamp,
        "plan_id": plan_id,
        "plans": health[:max_plans],
        "attention": attention_all[:max_attention],
        "sessions": session_rows,
        "claims": claim_rows,
        "overlaps": overlap_rows,
        "counts": counts,
        "needs_me_task_ids": sorted(attention_task_ids),
        "needs_me_plan_ids": sorted(needs_me_plan_ids),
    }
