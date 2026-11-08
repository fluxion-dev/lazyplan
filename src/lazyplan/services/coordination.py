"""Coordination use cases: next, claim, renew, release, block, and unblock."""

from __future__ import annotations

from ..core.entities import Claim, Status, Task
from ..core.errors import ClaimConflict, TouchpointOverlap
from ..core.policies.coordination import parse_ttl, patterns_overlap, validate_block
from ..core.ports.coordination import CoordinationPort
from ..core.serialization import to_payload
from ..infrastructure.repo_paths import normalize_repo_path
from .planning import set_status


def overlaps(port: CoordinationPort, task_id: int) -> list[dict]:
    """Active claims whose touch-points overlap this task in the same repo."""
    patterns = port.list_touchpoints(task_id)
    if not patterns:
        return []
    roots = {
        normalize_repo_path(str(repo["repo_path"]))
        for repo in port.effective_repos("task", task_id)
    }
    found: list[dict] = []
    for claim in port.list_claims(include_expired=False):
        other_task = int(claim["task_id"])
        if other_task == task_id:
            continue
        claim_repo = normalize_repo_path(str(claim.get("repo_path") or ""))
        if claim_repo and roots and claim_repo not in roots:
            continue
        other = port.list_touchpoints(other_task)
        matched = sorted(
            {
                pattern
                for pattern in patterns
                for candidate in other
                if patterns_overlap(pattern, candidate)
            }
            | {
                candidate
                for pattern in patterns
                for candidate in other
                if patterns_overlap(pattern, candidate)
            }
        )
        if matched:
            found.append(
                {
                    "task_id": other_task,
                    "actor": str(claim.get("actor") or ""),
                    "patterns": matched,
                    "worktree": str(claim.get("worktree") or ""),
                    "repo_path": claim_repo,
                }
            )
    return found


def start_claim(
    port: CoordinationPort,
    task_id: int,
    actor: str,
    ttl: str | None = None,
    note: str = "",
    force: bool = False,
    worktree: str = "",
    repo_path: str = "",
    check_overlap: bool = True,
) -> dict:
    """Claim a task and move it doing; release the lease if the move fails."""
    if check_overlap and not force:
        found = overlaps(port, task_id)
        if found:
            first = found[0]
            raise TouchpointOverlap(
                task_id,
                int(first["task_id"]),
                str(first["actor"]),
                list(first["patterns"]),
            )
    seconds = parse_ttl(ttl)
    claim, previous = port.claim_task(
        task_id,
        actor,
        ttl_seconds=seconds,
        note=note,
        force=force,
        worktree=worktree,
        repo_path=repo_path,
    )
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
    worktree: str = "",
    repo_path: str = "",
) -> dict | None:
    """Select and optionally claim the first eligible todo, retrying lost races."""
    for _ in range(100):
        tasks = port.claimable_tasks(plan_id)
        if not tasks:
            return None
        task = next((item for item in tasks if not overlaps(port, item.id)), None)
        if task is None:
            return None
        if suggest:
            return {"claim": None, "task": to_payload(vars(task)), "previous": None}
        try:
            return start_claim(
                port,
                task.id,
                actor,
                ttl=ttl,
                note=note,
                worktree=worktree,
                repo_path=repo_path,
                check_overlap=False,
            )
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
    updated = port.set_blocked(task_id, True, reason, actor=actor)
    if updated is None:
        raise KeyError(f"task #{task_id} not found")
    if task.status == Status.DOING:
        set_status(port, "task", task_id, Status.TODO, actor=actor)
        updated = port.get_task(task_id) or updated
    elif port.get_claim(task_id) is not None:
        port.release_claim(task_id, actor, force=True)
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
