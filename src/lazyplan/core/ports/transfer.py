"""The transfer repository port: stable UIDs and provider issue links."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from ..entities import Claim, ExternalRef, Plan, Session, Task
from .provenance import ProvenancePort


class TransferPort(ProvenancePort, Protocol):
    """Export, import, sync, share, and issue-intake surface."""

    def get_plan_by_uid(self, uid: str) -> Plan | None: ...

    def set_plan_uid(self, pid: int, uid: str) -> bool: ...

    def set_plan_archived(self, plan_id: int, archived_at: float, actor: str = "human") -> bool: ...

    def plan_uids_map(self) -> dict[int, str]: ...

    def restore_claim(
        self,
        task_id: int,
        actor: str,
        started_at: float,
        expires_at: float,
        renewed_at: float = 0,
        note: str = "",
    ) -> bool: ...

    def claims_map(self) -> dict[int, Claim]: ...

    def issue_links_map(self) -> dict[tuple[str, int], list[dict]]: ...

    def refs_map(self) -> dict[int, list[ExternalRef]]: ...

    def link_ref(
        self,
        plan_id: int,
        url: str,
        provider: str = "",
        kind: str = "issue",
        external_id: str = "",
        title: str = "",
        state: str = "",
        actor: str = "human",
        now: float | None = None,
    ) -> ExternalRef: ...

    def transaction(self) -> AbstractContextManager[None]: ...

    def all_criterion_links(self) -> list[dict]: ...

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
        archived: str = "hide",
    ) -> list[Session]: ...

    def restore_session_history(self, row: dict, actor: str = "human") -> int | None: ...

    def set_blocked(
        self, tid: int, blocked: bool, reason: str = "", actor: str = "human"
    ) -> Task | None: ...

    def add_issue_link(
        self,
        provider: str,
        external_id: str,
        number: str,
        url: str,
        title: str,
        state: str,
        row_kind: str,
        row_id: int,
        updated_at: float = 0,
    ) -> dict: ...

    def get_issue_link(self, provider: str, external_id: str) -> dict | None: ...

    def list_issue_links(self, row_kind: str, row_id: int) -> list[dict]: ...

    def update_issue_link(
        self, provider: str, external_id: str, title: str, url: str, state: str, updated_at: float
    ) -> bool: ...
