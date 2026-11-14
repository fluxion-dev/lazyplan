"""The transfer repository port: stable UIDs and provider issue intake."""

from __future__ import annotations

from typing import Protocol

from ..entities import Plan
from .claims import BlockedPort, ClaimsPort
from .provenance import ProvenancePort
from .refs import RefsPort
from .sessions import SessionsPort


class TransferPort(
    ProvenancePort,
    RefsPort,
    ClaimsPort,
    BlockedPort,
    SessionsPort,
    Protocol,
):
    """Export, import, sync, share, and issue-intake surface."""

    def get_plan_by_uid(self, uid: str) -> Plan | None: ...

    def set_plan_uid(self, pid: int, uid: str) -> bool: ...

    def set_plan_archived(self, plan_id: int, archived_at: float, actor: str = "human") -> bool: ...

    def plan_uids_map(self) -> dict[int, str]: ...
