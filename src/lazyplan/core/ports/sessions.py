"""The legacy session history port: read-only rows plus archive and restore."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..entities import Session
from .planning import PlanningPort


class SessionsReadPort(Protocol):
    """Read surface for archived session history."""

    def get_session(self, session_id: int) -> Session | None: ...

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
        archived: str = "hide",
    ) -> list[Session]: ...

    def events_for_session(self, session_id: int, limit: int = 50) -> list[dict]: ...


class SessionsPort(SessionsReadPort, PlanningPort, Protocol):
    """Archive and restore surface for session history."""

    def archive_sessions(
        self, session_ids: Sequence[int], actor: str = ..., now: float | None = ...
    ) -> int: ...

    def restore_session(
        self, session_id: int, actor: str = ..., now: float | None = ...
    ) -> bool: ...

    def restore_session_history(self, row: dict, actor: str = ...) -> int | None: ...
