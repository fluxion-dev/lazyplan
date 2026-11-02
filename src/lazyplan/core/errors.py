"""Domain errors shared by the pure core and its adapters."""

from __future__ import annotations

from .entities import Claim


class ClaimError(RuntimeError):
    """Base error for lease operations."""


class ClaimConflict(ClaimError):
    """A task is held by another actor, or a lease cannot be changed."""

    def __init__(self, claim: Claim, reason: str = "held") -> None:
        self.claim = claim
        self.reason = reason
        super().__init__(
            f"task #{claim.task_id} is claimed by {claim.actor} "
            f"until {int(claim.expires_at)} ({reason})"
        )


class ClaimMissing(ClaimError):
    """No lease exists for the task."""
