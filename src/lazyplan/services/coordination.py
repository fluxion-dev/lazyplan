"""Coordination use cases: next, claim, renew, release, block, and unblock."""

from __future__ import annotations

from ..core.entities import Claim, Status, Task
from ..core.errors import ClaimConflict
from ..core.policies.coordination import parse_ttl, validate_block
from ..core.ports.coordination import CoordinationPort
from ..core.serialization import to_payload
from .planning import set_status


def start_claim(
    port: CoordinationPort,
    task_id: int,
    actor: str,
    ttl: str | None = None,
    note: str = "",
    force: bool = False,
) -> dict:
    """Claim a task and move it doing; release the lease if the move fails."""
    seconds = parse_ttl(ttl)
    claim, previous = port.claim_task(task_id, actor, ttl_seconds=seconds, note=note, force=force)
    try:
        set_status(port, "task", task_id, Status.DOING, actor=actor)
    except Exception:
        port.release_claim(task_id, actor, force=True)
        raise
    task = port.get_task(task_id)
    return {
        "claim": vars(claim),
        "task": to_payload(vars(task)) if task is not None else None,
        "previous": vars(previous) if previous is not None else None,
    }


def renew_task_claim(
    port: CoordinationPort, task_id: int, actor: str, ttl: str | None = None
) -> Claim:
    """Extend a lease held by this actor."""
    return port.renew_claim(task_id, actor, ttl_seconds=parse_ttl(ttl))


def release_task_claim(
    port: CoordinationPort, task_id: int, actor: str, force: bool = False
) -> dict:
    """Release a lease and return the released claim with task context."""
    task = port.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    claim = port.release_claim(task_id, actor, force=force)
    return {
        "claim": vars(claim) if claim is not None else None,
        "task": to_payload(vars(task)),
    }


def claim_next(
    port: CoordinationPort,
    actor: str,
    plan_id: int | None = None,
    ttl: str | None = None,
    note: str = "",
    suggest: bool = False,
) -> dict | None:
    """Select and optionally claim the first eligible todo, retrying lost races."""
    for _ in range(100):
        task = port.next_claimable_task(plan_id)
        if task is None:
            return None
        if suggest:
            return {"claim": None, "task": to_payload(vars(task)), "previous": None}
        try:
            return start_claim(port, task.id, actor, ttl=ttl, note=note)
        except ClaimConflict:
            # Another process claimed this task between selection and claim.
            continue
    return None


def block_task(port: CoordinationPort, task_id: int, reason: str, actor: str = "human") -> Task:
    """Block a task, release its lease, and record the reason as a note."""
    task = port.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    validate_block(task, reason)
    if port.get_claim(task_id) is not None:
        port.release_claim(task_id, actor, force=True)
    updated = port.set_blocked(task_id, True, reason, actor=actor)
    if updated is None:
        raise KeyError(f"task #{task_id} not found")
    if task.status == Status.DOING:
        set_status(port, "task", task_id, Status.TODO, actor=actor)
        updated = port.get_task(task_id) or updated
    port.add_note("task", task_id, f"Blocked: {reason.strip()}", actor=actor)
    return updated


def unblock_task(port: CoordinationPort, task_id: int, actor: str = "human") -> Task:
    """Clear the blocked flag and leave the task in the todo pool."""
    task = port.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    updated = port.set_blocked(task_id, False, "", actor=actor)
    if updated is None:
        raise KeyError(f"task #{task_id} not found")
    port.add_note("task", task_id, "Unblocked", actor=actor)
    return updated


def list_claims(
    port: CoordinationPort,
    include_expired: bool = False,
    plan_id: int | None = None,
) -> list[dict]:
    """Lease rows with task and plan context."""
    return port.list_claims(include_expired=include_expired, plan_id=plan_id)


def release_claim(
    port: CoordinationPort, task_id: int, actor: str, force: bool = False
) -> Claim | None:
    """Release a raw lease, preserving bulk undo semantics."""
    return port.release_claim(task_id, actor, force=force)


def set_blocked(
    port: CoordinationPort,
    task_id: int,
    blocked: bool,
    reason: str = "",
    actor: str = "human",
) -> Task | None:
    """Set the blocked flag without the note and status side effects."""
    return port.set_blocked(task_id, blocked, reason, actor=actor)


__all__ = [
    "block_task",
    "claim_next",
    "list_claims",
    "parse_ttl",
    "release_claim",
    "release_task_claim",
    "renew_task_claim",
    "set_blocked",
    "start_claim",
    "unblock_task",
]
