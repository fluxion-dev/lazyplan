"""The claim side of moving a task to doing: who may, and taking the lease."""

from __future__ import annotations

import time

from ..core.entities import Claim
from ..core.ports.planning import PlanningPort


def check_claimable(claim: Claim | None, task_id: int, actor: str) -> None:
    """Refuse doing while another actor's live claim holds the task."""
    if claim is not None and not claim.expired(time.time()) and claim.actor != actor:
        raise ValueError(
            f"task #{task_id} is claimed by {claim.actor}; take it over with"
            f" `lpui claim --id {task_id} --force`"
        )


def claim_for_doing(port: PlanningPort, claim: Claim | None, task_id: int, actor: str) -> None:
    """Claim a task that just moved to doing, unless the actor already holds it."""
    claim_task = getattr(port, "claim_task", None)
    if claim_task is None:
        return
    if claim is not None and not claim.expired(time.time()) and claim.actor == actor:
        return
    checkout = port.checkout_path()
    claim_task(task_id, actor, worktree=checkout, repo_path=checkout, force=True)
