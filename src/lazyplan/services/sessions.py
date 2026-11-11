"""Session use cases: lifecycle, state, and compact reads."""

from __future__ import annotations

import time

from ..core.entities import Session
from ..core.policies.sessions import IDLE_AFTER_SECS, STALE_AFTER_SECS
from ..core.ports.sessions import SessionsPort, SessionsReadPort


def session_state(
    session: Session,
    now: float | None = None,
    idle_after: float = IDLE_AFTER_SECS,
) -> str:
    """One of ``ended``, ``auto-closed``, ``idle``, ``stale``, ``awaiting``, or ``working``."""
    if session.ended:
        return "auto-closed" if session.auto_closed else "ended"
    stamp = time.time() if now is None else now
    idle = session.idle_seconds(stamp)
    if idle >= idle_after:
        return "idle"
    if idle >= STALE_AFTER_SECS:
        return "stale"
    return "awaiting" if session.awaiting else "working"


def start_session(
    port: SessionsPort,
    actor: str,
    plan_id: int | None = None,
    repo_path: str = "",
    branch: str = "",
    note: str = "",
    force: bool = False,
    host: str = "",
    host_session: str = "",
    phase: str = "working",
    plan_source: str = "auto",
) -> dict:
    """Open a session and return it with any superseded session."""
    session, previous = port.start_session(
        actor,
        plan_id=plan_id,
        repo_path=repo_path,
        branch=branch,
        note=note,
        force=force,
        host=host,
        host_session=host_session,
        phase=phase,
        plan_source=plan_source,
    )
    return {"session": session, "previous": previous}


def end_session(
    port: SessionsPort,
    session_id: int,
    actor: str,
    summary: str = "",
    handoff: str = "",
    auto: bool = False,
) -> Session:
    """Close one session with a summary and handoff."""
    return port.end_session(session_id, actor, summary=summary, handoff=handoff, auto=auto)


def touch_session(
    port: SessionsPort,
    session_id: int,
    phase: str | None = None,
    host: str = "",
    branch: str | None = None,
    plan_id: int | None = None,
    replace_plan: bool = False,
) -> Session | None:
    """Refresh one session's heartbeat and optional attribution."""
    return port.touch_session(
        session_id,
        phase=phase,
        host=host,
        branch=branch,
        plan_id=plan_id,
        replace_plan=replace_plan,
    )


def open_session_for(
    port: SessionsPort,
    repo_path: str,
    host: str = "",
    actor: str = "",
) -> Session | None:
    """Newest open session in one checkout, preferring a matching host."""
    return port.open_session_for(repo_path, host=host, actor=actor)


def reap_idle_sessions(
    port: SessionsPort,
    now: float | None = None,
    idle_after: float = IDLE_AFTER_SECS,
    repo_path: str = "",
) -> list[Session]:
    """Close abandoned sessions and return the ones that ended."""
    return port.reap_idle_sessions(now=now, idle_after=idle_after, repo_path=repo_path)


def current_session(port: SessionsReadPort, actor: str) -> Session | None:
    """The session this actor's writes would tag, if any."""
    return port.active_session(actor)


def show_session(port: SessionsReadPort, session_id: int, limit: int = 50) -> dict | None:
    """One session with its events and action counts."""
    session = port.get_session(session_id)
    if session is None:
        return None
    return {
        "session": session,
        "events": port.events_for_session(session_id, limit=limit),
        "counts": port.session_counts(session_id),
    }


def list_sessions(
    port: SessionsReadPort,
    actor: str = "",
    plan_id: int | None = None,
    open_only: bool = False,
    limit: int = 20,
) -> list[Session]:
    """Recent sessions, newest first."""
    return port.list_sessions(actor=actor, plan_id=plan_id, open_only=open_only, limit=limit)


def previous_session(
    port: SessionsReadPort,
    plan_id: int | None = None,
    actor: str = "",
    repo_path: str = "",
) -> dict | None:
    """Most recently ended session as a compact resume block."""
    row = port.latest_ended_session(plan_id=plan_id, actor=actor, repo_path=repo_path)
    if row is None:
        return None
    return {
        "id": row.id,
        "actor": row.actor,
        "ended_at": row.ended_at,
        "summary": row.summary,
        "handoff": row.handoff,
    }
