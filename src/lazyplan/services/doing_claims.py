"""The claim side of moving a task to doing: who may, and taking the lease."""

from __future__ import annotations

import time

from ..core.entities import Claim
from ..core.ports.planning import PlanningPort
from .worktrees import lane_busy, lane_gate


def check_claimable(
    port: PlanningPort,
    claim: Claim | None,
    task_id: int,
    actor: str,
    worktree: str = "",
    check_lane: bool = True,
) -> None:
    """Refuse doing while another actor holds the task or the lane is wrong."""
    if claim is not None and not claim.expired(time.time()) and claim.actor != actor:
        raise ValueError(
            f"task #{task_id} is claimed by {claim.actor}; take it over with"
            f" `lpui claim --id {task_id} --force`"
        )
    if check_lane:
        blocker = lane_gate(port, task_id, worktree)
        if blocker:
            raise ValueError(blocker)
        busy = lane_busy(port, task_id)
        if busy:
            raise ValueError(busy)


def claim_for_doing(
    port: PlanningPort, claim: Claim | None, task_id: int, actor: str, worktree: str = ""
) -> None:
    """Claim a task that just moved to doing, unless the actor already holds it."""
    claim_task = getattr(port, "claim_task", None)
    if claim_task is None:
        return
    if claim is not None and not claim.expired(time.time()) and claim.actor == actor:
        return
    checkout = worktree or port.checkout_path()
    claim_task(task_id, actor, worktree=checkout, repo_path=checkout, force=True)
