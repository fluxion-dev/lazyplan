"""Read-only flow stats from existing events and rows.

No estimates, no forecasts, no writes. Cycle time uses status events only;
missing timestamps are omitted rather than invented.
"""

from __future__ import annotations

import re
import statistics
import time

from ..core.entities import Claim, Status, Task
from ..core.policies.planning import rollup_target
from ..core.ports.insights import InsightsPort

_ADDED = re.compile(r"^T#(\d+) ")
_STATUS = re.compile(r"^task #(\d+) -> (todo|doing|done)$")


def _events(store: InsightsPort) -> list[dict]:
    """All events oldest first."""
    return list(reversed(store.feed(limit=1_000_000)))


def _all_tasks(store: InsightsPort) -> list[Task]:
    """Every task under a live plan, in creation order."""
    milestones = store.milestones_map()
    tasks = store.tasks_map()
    return [
        task
        for plan in store.list_plans(archived="hide")
        for milestone in milestones.get(plan.id, ())
        for task in tasks.get(milestone.id, ())
    ]


def _event_maps(
    events: list[dict],
    task_ids: set[int] | None = None,
) -> tuple[dict[int, float], dict[int, list[tuple[float, str, str]]]]:
    """Task add times and status transitions from the event stream."""
    added: dict[int, float] = {}
    transitions: dict[int, list[tuple[float, str, str]]] = {}
    for event in events:
        detail = str(event.get("detail") or "")
        actor_name = str(event.get("actor") or "")
        found = _ADDED.match(detail)
        if found is not None:
            task_id = int(found.group(1))
            if task_ids is None or task_id in task_ids:
                added.setdefault(task_id, float(event["ts"]))
            continue
        found = _STATUS.match(detail)
        if found is not None:
            task_id = int(found.group(1))
            if task_ids is None or task_id in task_ids:
                transitions.setdefault(task_id, []).append(
                    (float(event["ts"]), found.group(2), actor_name)
                )
    return added, transitions


def _current_metrics(
    tasks: list[Task], added: dict[int, float], stale_before: float, now: float
) -> tuple[int, int, int]:
    """WIP, blocked, stale todo count, and aging doing minutes."""
    wip = sum(1 for task in tasks if task.status.value == "doing")
    blocked = sum(1 for task in tasks if task.blocked)
    stale = sum(
        1
        for task in tasks
        if task.status.value == "todo" and added.get(task.id, now) < stale_before
    )
    return wip, blocked, stale


def _activity_metrics(
    transitions: dict[int, list[tuple[float, str, str]]],
    added: dict[int, float],
    since: float,
    actor: str | None,
) -> tuple[list[float], list[float], int]:
    """Done times, cycle minutes, and reopened count for the window/actor."""
    done_times: list[float] = []
    cycles: list[float] = []
    reopened = 0
    for task_id, changes in transitions.items():
        relevant = [
            (when, status) for when, status, who in changes if actor is None or who == actor
        ]
        done = [when for when, status in relevant if status == "done"]
        if done and done[-1] >= since:
            done_times.append(done[-1])
            first_doing = next((when for when, status in relevant if status == "doing"), None)
            start = first_doing if first_doing is not None else added.get(task_id)
            if start is not None and done[-1] >= start:
                cycles.append((done[-1] - start) / 60)
        seen_done = False
        for _when, status in relevant:
            if status == "done":
                seen_done = True
            elif seen_done and status == "doing":
                reopened += 1
                seen_done = False
    return done_times, cycles, reopened


ATTENTION_STALE_SECS = 24 * 3600


def _task_attention(
    task: Task,
    claim: Claim | None,
    transitions: list[tuple[float, str, str]],
    open_criteria: set[int],
    links: list,
    stamp: float,
    stale_after: float,
) -> list[str]:
    """Reasons one task needs attention, in display order."""
    found: list[str] = []
    if claim is not None and claim.expired(stamp):
        found.append("stale claim")
    if task.blocked:
        found.append("blocked")
    if task.status.value == "doing":
        starts = [when for when, status, _actor in transitions if status == "doing"]
        if starts and stamp - starts[-1] > stale_after:
            found.append("aging doing")
    if task.status.value == "done" and task.id in open_criteria:
        found.append("done with open criteria")
    if any(str(link.checks or "") == "fail" for link in links):
        found.append("failing checks")
    return found


def attention_reasons(
    store: InsightsPort,
    stale_after: float = ATTENTION_STALE_SECS,
    now: float | None = None,
    *,
    tasks: list[Task] | None = None,
    claims: dict[int, Claim] | None = None,
    forge: dict | None = None,
    open_criteria: set[int] | None = None,
) -> dict[int, list[str]]:
    """Task ids the TUI should surface as needing attention, with reasons."""
    stamp = time.time() if now is None else now
    task_rows = tasks if tasks is not None else _all_tasks(store)
    _added, transitions = _event_maps(_events(store), {task.id for task in task_rows})
    claims = claims if claims is not None else store.claims_map()
    forge = forge if forge is not None else store.forge_links_map()
    open_criteria = open_criteria if open_criteria is not None else store.open_task_criteria_ids()
    reasons: dict[int, list[str]] = {}
    for task in task_rows:
        found = _task_attention(
            task,
            claims.get(task.id),
            transitions.get(task.id, []),
            open_criteria,
            forge.get(("task", task.id), []),
            stamp,
            stale_after,
        )
        if found:
            reasons[task.id] = found
    return reasons


def attention_ids(
    store: InsightsPort, stale_after: float = ATTENTION_STALE_SECS, now: float | None = None
) -> set[int]:
    """Task ids the TUI should surface as needing attention."""
    return set(attention_reasons(store, stale_after=stale_after, now=now))


def drift_summary(store: InsightsPort, now: float | None = None) -> dict[str, list]:
    """Parent-status drift, expired claims, and done rows with open criteria."""
    stamp = time.time() if now is None else now
    milestones_by_plan = store.milestones_map()
    tasks_by_milestone = store.tasks_map()
    parent: list[dict] = []
    for plan in store.list_plans(archived="hide"):
        for milestone in milestones_by_plan.get(plan.id, []):
            kids = [task.status for task in tasks_by_milestone.get(milestone.id, [])]
            if kids:
                target = rollup_target(kids)
                if target != milestone.status:
                    parent.append({"kind": "milestone", "id": milestone.id, "to": target.value})
        kids = [milestone.status for milestone in milestones_by_plan.get(plan.id, [])]
        if kids:
            target = rollup_target(kids)
            if target != plan.status:
                parent.append({"kind": "plan", "id": plan.id, "to": target.value})
    open_ids = store.open_task_criteria_ids()
    open_criteria = [
        task.id for task in _all_tasks(store) if task.status == Status.DONE and task.id in open_ids
    ]
    expired = [task_id for task_id, claim in store.claims_map().items() if claim.expired(stamp)]
    return {
        "parent_status": parent,
        "expired_claims": expired,
        "open_criteria": open_criteria,
    }


def compute(
    store: InsightsPort,
    since: float,
    stale_before: float,
    actor: str | None = None,
    now: float | None = None,
) -> dict:
    """Compute current flow metrics plus actor-filtered completion metrics."""
    stamp = time.time() if now is None else now
    tasks = _all_tasks(store)
    added, transitions = _event_maps(_events(store), {task.id for task in tasks})
    wip, blocked, stale = _current_metrics(tasks, added, stale_before, stamp)
    aging: list[float] = []
    for task in tasks:
        if task.status.value != "doing":
            continue
        starts = [
            when for when, status, _actor in transitions.get(task.id, []) if status == "doing"
        ]
        if starts:
            aging.append(max(0.0, (stamp - starts[-1]) / 60))
    done_times, cycles, reopened = _activity_metrics(transitions, added, since, actor)
    claims = store.list_claims(now=stamp)
    if actor is not None:
        claims = [claim for claim in claims if claim["actor"] == actor]
    return {
        "since": since,
        "actor": actor,
        "wip": wip,
        "cycle_median_minutes": round(statistics.median(cycles), 1) if cycles else 0.0,
        "throughput": len(done_times),
        "aging_median_minutes": round(statistics.median(aging), 1) if aging else 0.0,
        "aging_max_minutes": round(max(aging), 1) if aging else 0.0,
        "stale_todos": stale,
        "reopened": reopened,
        "claims": len(claims),
        "blocked": blocked,
        "drift": drift_summary(store, now=stamp),
    }
