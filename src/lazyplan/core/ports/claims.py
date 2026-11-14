"""The claims port: leases over tasks plus the blocked flag."""

from __future__ import annotations

from typing import Protocol

from ..entities import Claim, Task


class ClaimsReadPort(Protocol):
    """Claim reads used by context, brief, stats, and the tracker."""

    def get_claim(self, task_id: int) -> Claim | None: ...

    def claims_map(self) -> dict[int, Claim]: ...

    def list_claims(
        self,
        include_expired: bool = False,
        now: float | None = None,
        plan_id: int | None = None,
    ) -> list[dict]: ...


class ClaimsPort(ClaimsReadPort, Protocol):
    """Lease writes used by claim, next, renew, release, and transfer."""

    def claim_task(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = ...,
        note: str = "",
        force: bool = False,
        now: float | None = None,
        worktree: str = "",
        repo_path: str = "",
    ) -> tuple[Claim, Claim | None]: ...

    def renew_claim(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = ...,
        now: float | None = None,
        log: bool = ...,
    ) -> Claim: ...

    def release_claim(self, task_id: int, actor: str, force: bool = False) -> Claim | None: ...

    def restore_claim(
        self,
        task_id: int,
        actor: str,
        started_at: float,
        expires_at: float,
        renewed_at: float = 0,
        note: str = "",
    ) -> bool: ...

    def claimable_tasks(
        self, plan_id: int | None = None, now: float | None = None
    ) -> list[Task]: ...


class BlockedPort(Protocol):
    """The blocked flag, shared by coordination and transfer."""

    def set_blocked(
        self, tid: int, blocked: bool, reason: str = "", actor: str = "human"
    ) -> Task | None: ...
