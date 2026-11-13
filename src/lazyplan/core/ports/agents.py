"""The agent registry port: live rows, transitions, and session history."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ..entities import Agent, AgentEvent, Session
from .planning import PlanningPort


class AgentsReadPort(Protocol):
    """Read surface used by context, brief, hooks, and the tracker."""

    def get_agent(self, agent_id: int) -> Agent | None: ...

    def list_agents(
        self,
        plan_id: int | None = None,
        task_id: int | None = None,
        open_only: bool = False,
        live_only: bool = False,
        host: str = "",
        status: str = "",
        limit: int = 50,
        archived: str = "hide",
    ) -> list[Agent]: ...

    def agents_for_host(
        self, host: str, host_session: str, open_only: bool = True
    ) -> list[Agent]: ...

    def child_agents(self, parent_id: int, open_only: bool = False) -> list[Agent]: ...

    def latest_ended_agent(
        self, plan_id: int | None = None, actor: str = "", repo_path: str = ""
    ) -> Agent | None: ...

    def agent_events(self, agent_id: int, limit: int = 50) -> list[AgentEvent]: ...

    def agent_event_counts(self, agent_id: int) -> dict[str, int]: ...

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


class AgentsPort(AgentsReadPort, PlanningPort, Protocol):
    """Write surface used by the agent commands, hooks, and maintenance."""

    def add_agent(
        self,
        actor: str,
        host: str = ...,
        host_session: str = ...,
        agent: str = ...,
        role: str = ...,
        model: str = ...,
        parent_id: int | None = ...,
        pid: int = ...,
        process_start: str = ...,
        repo_path: str = ...,
        worktree: str = ...,
        branch: str = ...,
        head_sha: str = ...,
        plan_id: int | None = ...,
        task_id: int | None = ...,
        status: str = ...,
        unbound_reason: str = ...,
        note: str = ...,
        now: float | None = ...,
    ) -> Agent: ...

    def patch_agent(self, agent_id: int, now: float | None = ..., **fields: object) -> Agent: ...

    def transition_agent(
        self,
        agent_id: int,
        status: str,
        event: str = ...,
        detail: str = ...,
        summary: str = ...,
        handoff: str = ...,
        now: float | None = ...,
    ) -> Agent: ...

    def open_agents_with_pids(self) -> list[Agent]: ...

    def end_agent(
        self,
        agent_id: int,
        actor: str,
        summary: str = ...,
        handoff: str = ...,
        now: float | None = ...,
    ) -> Agent: ...

    def archive_sessions(
        self, session_ids: Sequence[int], actor: str = ..., now: float | None = ...
    ) -> int: ...

    def restore_session(
        self, session_id: int, actor: str = ..., now: float | None = ...
    ) -> bool: ...

    def restore_session_history(self, row: dict, actor: str = ...) -> int | None: ...
