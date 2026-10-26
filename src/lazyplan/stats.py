"""Read-only flow stats from existing events and rows.

No estimates, no forecasts, no writes. Cycle time uses status events only;
missing timestamps are omitted rather than invented.
"""

from __future__ import annotations

import re
import statistics
import time

from .store import Store

_ADDED = re.compile(r"^T#(\d+) ")
_STATUS = re.compile(r"^task #(\d+) -> (todo|doing|done)$")


def _events(store: Store) -> list[dict]:
    """All events oldest first."""
    return list(reversed(store.feed(limit=1_000_000)))


def _event_maps(
    events: list[dict],
) -> tuple[dict[int, float], dict[int, list[tuple[float, str, str]]]]:
    """Task add times and status transitions from the event stream."""
    added: dict[int, float] = {}
    transitions: dict[int, list[tuple[float, str, str]]] = {}
    for event in events:
        detail = str(event.get("detail") or "")
        actor_name = str(event.get("actor") or "")
        found = _ADDED.match(detail)
        if found is not None:
            added.setdefault(int(found.group(1)), float(event["ts"]))
            continue
        found = _STATUS.match(detail)
        if found is not None:
            transitions.setdefault(int(found.group(1)), []).append(
                (float(event["ts"]), found.group(2), actor_name)
            )
    return added, transitions


def _current_metrics(
    tasks: list, added: dict[int, float], stale_before: float, now: float
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


def attention_ids(
    store: Store, stale_after: float = ATTENTION_STALE_SECS, now: float | None = None
) -> set[int]:
    """Task ids the TUI should surface as needing attention."""
    stamp = time.time() if now is None else now
    _added, transitions = _event_maps(_events(store))
    claims = store.claims_map()
    forge = store.forge_links_map()
    ids: set[int] = set()
    for plan in store.list_plans():
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                claim = claims.get(task.id)
                if claim is not None and claim.expired(stamp):
                    ids.add(task.id)
                if task.blocked:
                    ids.add(task.id)
                if task.status.value == "doing":
                    starts = [
                        when
                        for when, status, _actor in transitions.get(task.id, [])
                        if status == "doing"
                    ]
                    if starts and stamp - starts[-1] > stale_after:
                        ids.add(task.id)
                if task.status.value == "done" and store.open_criteria("task", task.id):
                    ids.add(task.id)
                links = forge.get(("task", task.id), [])
                if any(str(link.checks or "") == "fail" for link in links):
                    ids.add(task.id)
    return ids


def compute(
    store: Store,
    since: float,
    stale_before: float,
    actor: str | None = None,
    now: float | None = None,
) -> dict:
    """Compute current flow metrics plus actor-filtered completion metrics."""
    stamp = time.time() if now is None else now
    added, transitions = _event_maps(_events(store))
    tasks = [
        task
        for plan in store.list_plans()
        for milestone in store.list_milestones(plan.id)
        for task in store.list_tasks(milestone.id)
    ]
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
    }
