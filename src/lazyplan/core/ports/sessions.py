"""The sessions port: lifecycle, reads, and event lookup."""

from __future__ import annotations

from typing import Protocol

from ..entities import Session
from .planning import PlanningPort


class SessionsReadPort(Protocol):
    """Read surface used by context, brief, and hooks."""

    def get_session(self, session_id: int) -> Session | None: ...

    def active_session(self, actor: str) -> Session | None: ...

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
    ) -> list[Session]: ...

    def latest_ended_session(
        self,
        plan_id: int | None = None,
        actor: str = "",
        repo_path: str = "",
    ) -> Session | None: ...

    def events_for_session(self, session_id: int, limit: int = 50) -> list[dict]: ...

    def session_counts(self, session_id: int) -> dict[str, int]: ...


class SessionsPort(SessionsReadPort, PlanningPort, Protocol):
    """Write surface used by the session commands."""

    def start_session(
        self,
        actor: str,
        plan_id: int | None = None,
        repo_path: str = "",
        branch: str = "",
        note: str = "",
        force: bool = False,
        now: float | None = None,
        host: str = "",
        phase: str = "working",
    ) -> tuple[Session, Session | None]: ...

    def end_session(
        self,
        session_id: int,
        actor: str,
        summary: str = "",
        handoff: str = "",
        now: float | None = None,
        auto: bool = False,
    ) -> Session: ...

    def touch_session(
        self,
        session_id: int,
        phase: str | None = None,
        host: str = "",
        now: float | None = None,
    ) -> Session | None: ...

    def open_session_for(
        self,
        repo_path: str,
        host: str = "",
        actor: str = "",
    ) -> Session | None: ...

    def bind_session(
        self,
        host: str,
        host_session: str,
        project: str,
        repo_path: str,
        session_id: int,
        now: float | None = None,
    ) -> None: ...

    def session_for_project(self, project: str, host: str = "") -> Session | None: ...

    def detach_host_binding(
        self,
        host: str,
        host_session: str,
        project: str,
    ) -> tuple[Session | None, bool]: ...

    def reap_idle_sessions(
        self,
        now: float | None = None,
        idle_after: float = ...,
        repo_path: str = "",
    ) -> list[Session]: ...
