"""Claims services."""

from __future__ import annotations

import re

from ..models import Claim, Status, Task
from ..store import CLAIM_DEFAULT_TTL, ClaimConflict, Store, to_payload
from .plans import set_status

_TTL_UNITS = {
    None: 1,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}
_TTL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\.?\s*([a-z]+)?\s*$", re.IGNORECASE)


def parse_ttl(text: str | None, default: float = CLAIM_DEFAULT_TTL) -> float:
    """Parse a lease TTL such as `30m`, `2.hours`, `90s`, or `1.days`."""
    if not text:
        return float(default)
    match = _TTL_RE.match(text)
    if match is None:
        raise ValueError(f"invalid ttl {text!r}; use 30m, 2.hours, or seconds")
    unit = (match.group(2) or "s").lower()
    if unit not in _TTL_UNITS:
        raise ValueError(f"unknown ttl unit {unit!r}; use s, m, h, d, or w")
    seconds = float(match.group(1)) * _TTL_UNITS[unit]
    if seconds <= 0:
        raise ValueError("claim ttl must be positive")
    return seconds


def start_claim(
    store: Store,
    task_id: int,
    actor: str,
    ttl: str | None = None,
    note: str = "",
    force: bool = False,
) -> dict:
    """Claim a task and move it doing; release the lease if the move fails."""
    seconds = parse_ttl(ttl)
    claim, previous = store.claim_task(task_id, actor, ttl_seconds=seconds, note=note, force=force)
    try:
        set_status(store, "task", task_id, Status.DOING, actor=actor)
    except Exception:
        store.release_claim(task_id, actor, force=True)
        raise
    task = store.get_task(task_id)
    return {
        "claim": vars(claim),
        "task": to_payload(vars(task)) if task is not None else None,
        "previous": vars(previous) if previous is not None else None,
    }


def renew_task_claim(store: Store, task_id: int, actor: str, ttl: str | None = None) -> Claim:
    """Extend a lease held by this actor."""
    return store.renew_claim(task_id, actor, ttl_seconds=parse_ttl(ttl))


def release_task_claim(store: Store, task_id: int, actor: str, force: bool = False) -> dict:
    """Release a lease and return the released claim with task context."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    claim = store.release_claim(task_id, actor, force=force)
    return {
        "claim": vars(claim) if claim is not None else None,
        "task": to_payload(vars(task)),
    }


def claim_next(
    store: Store,
    actor: str,
    plan_id: int | None = None,
    ttl: str | None = None,
    note: str = "",
    suggest: bool = False,
) -> dict | None:
    """Select and optionally claim the first eligible todo, retrying lost races."""
    for _ in range(100):
        task = store.next_claimable_task(plan_id)
        if task is None:
            return None
        if suggest:
            return {"claim": None, "task": to_payload(vars(task)), "previous": None}
        try:
            return start_claim(store, task.id, actor, ttl=ttl, note=note)
        except ClaimConflict:
            # Another process claimed this task between selection and claim.
            continue
    return None


def block_task(store: Store, task_id: int, reason: str, actor: str = "human") -> Task:
    """Block a task, release its lease, and record the reason as a note."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    if task.status == Status.DONE:
        raise ValueError("cannot block a done task")
    if not reason.strip():
        raise ValueError("blocking a task needs a reason")
    if store.get_claim(task_id) is not None:
        store.release_claim(task_id, actor, force=True)
    updated = store.set_blocked(task_id, True, reason, actor=actor)
    if updated is None:
        raise KeyError(f"task #{task_id} not found")
    if task.status == Status.DOING:
        set_status(store, "task", task_id, Status.TODO, actor=actor)
        updated = store.get_task(task_id) or updated
    store.add_note("task", task_id, f"Blocked: {reason.strip()}", actor=actor)
    return updated


def unblock_task(store: Store, task_id: int, actor: str = "human") -> Task:
    """Clear the blocked flag and leave the task in the todo pool."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    updated = store.set_blocked(task_id, False, "", actor=actor)
    if updated is None:
        raise KeyError(f"task #{task_id} not found")
    store.add_note("task", task_id, "Unblocked", actor=actor)
    return updated
