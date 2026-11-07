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


class TouchpointOverlap(ClaimError):
    """A task's touch-points overlap another active claim."""

    def __init__(
        self,
        task_id: int,
        other_task: int,
        actor: str,
        patterns: list[str],
    ) -> None:
        self.task_id = task_id
        self.other_task = other_task
        self.actor = actor
        self.patterns = patterns
        joined = ", ".join(patterns)
        super().__init__(
            f"task #{task_id} overlaps active claim on task #{other_task} by {actor}: {joined}"
        )
