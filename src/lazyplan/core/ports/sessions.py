"""The sessions port: legacy session history and its archive lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..entities import Session


class SessionsReadPort(Protocol):
    """Session history reads used by agents, context, and the feed."""

    def get_session(self, session_id: int) -> Session | None: ...

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
        archived: str = "hide",
    ) -> list[Session]: ...

    def latest_ended_session(
        self, plan_id: int | None = None, actor: str = "", repo_path: str = ""
    ) -> Session | None: ...

    def events_for_session(self, session_id: int, limit: int = 50) -> list[dict]: ...

    def session_counts(self, session_id: int) -> dict[str, int]: ...


class SessionsPort(SessionsReadPort, Protocol):
    """Session history writes used by maintenance and transfer."""

    def archive_sessions(
        self, session_ids: Sequence[int], actor: str = ..., now: float | None = ...
    ) -> int: ...

    def restore_session(
        self, session_id: int, actor: str = ..., now: float | None = ...
    ) -> bool: ...

    def restore_session_history(self, row: dict, actor: str = "human") -> int | None: ...
