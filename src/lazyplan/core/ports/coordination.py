"""The coordination repository port: leases and blocked work."""

from __future__ import annotations

from typing import Protocol

from ..entities import Claim, Note, Task
from .planning import PlanningPort


class CoordinationPort(PlanningPort, Protocol):
    """Claim and blocked-work surface, on top of the planning read/write surface."""

    def claim_task(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = ...,
        note: str = "",
        force: bool = False,
        now: float | None = None,
    ) -> tuple[Claim, Claim | None]: ...

    def renew_claim(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = ...,
        now: float | None = None,
    ) -> Claim: ...

    def release_claim(self, task_id: int, actor: str, force: bool = False) -> Claim | None: ...

    def get_claim(self, task_id: int) -> Claim | None: ...

    def claims_map(self) -> dict[int, Claim]: ...

    def list_claims(
        self,
        include_expired: bool = False,
        now: float | None = None,
        plan_id: int | None = None,
    ) -> list[dict]: ...

    def next_claimable_task(
        self, plan_id: int | None = None, now: float | None = None
    ) -> Task | None: ...

    def set_blocked(
        self, tid: int, blocked: bool, reason: str = "", actor: str = "human"
    ) -> Task | None: ...

    def add_note(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Note: ...
