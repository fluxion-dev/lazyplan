"""Session use cases: start, end, and compact reads."""

from __future__ import annotations

from ..core.entities import Session
from ..core.ports.sessions import SessionsPort


def start_session(
    port: SessionsPort,
    actor: str,
    plan_id: int | None = None,
    repo_path: str = "",
    branch: str = "",
    note: str = "",
    force: bool = False,
) -> dict:
    """Open a session and return it with any superseded session."""
    session, previous = port.start_session(
        actor,
        plan_id=plan_id,
        repo_path=repo_path,
        branch=branch,
        note=note,
        force=force,
    )
    return {"session": session, "previous": previous}


def end_session(
    port: SessionsPort,
    session_id: int,
    actor: str,
    summary: str = "",
    handoff: str = "",
) -> Session:
    """Close one session with a summary and handoff."""
    return port.end_session(session_id, actor, summary=summary, handoff=handoff)


def current_session(port: SessionsPort, actor: str) -> Session | None:
    """The session this actor's writes would tag, if any."""
    return port.active_session(actor)


def show_session(port: SessionsPort, session_id: int, limit: int = 50) -> dict | None:
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
    port: SessionsPort,
    actor: str = "",
    plan_id: int | None = None,
    open_only: bool = False,
    limit: int = 20,
) -> list[Session]:
    """Recent sessions, newest first."""
    return port.list_sessions(actor=actor, plan_id=plan_id, open_only=open_only, limit=limit)
