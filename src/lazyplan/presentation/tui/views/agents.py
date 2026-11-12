"""Agent-session rows for the agents card.

Pure formatting: no Textual imports, so the CLI and tests can reuse the
state words without a terminal.
"""

from __future__ import annotations

import time

from .... import services
from ....core.entities import Session
from ...shared.design import escape_markup
from ...shared.session_labels import branch_label, plan_label, task_label

STATE_BADGES = {
    "working": "[green]▶ working[/]",
    "awaiting": "[yellow]◆ awaiting you[/]",
    "stale": "[yellow]◌ stale[/]",
    "idle": "[dim]◌ idle[/]",
    "ended": "[dim]ended[/]",
    "auto-closed": "[dim]auto-closed[/]",
}
_STATE_ORDER = {
    "awaiting": 0,
    "working": 1,
    "stale": 2,
    "idle": 3,
    "ended": 4,
    "auto-closed": 4,
}


def age(started_at: float, stamp: float) -> str:
    """Compact age: minutes until an hour, then hours and minutes."""
    minutes = int(max(0.0, stamp - started_at) / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


def rank_sessions(
    sessions: list[Session],
    now: float | None = None,
    idle_after: float | None = None,
) -> list[Session]:
    """Awaiting first, then working, then stale; newest first within a state."""
    stamp = time.time() if now is None else now

    def key(session: Session) -> tuple[int, float]:
        state = services.session_state(session, stamp, idle_after)
        return (_STATE_ORDER.get(state, 3), -session.started_at)

    return sorted(sessions, key=key)


def host_label(session: Session) -> str:
    """Host and short host-session id, when they add anything to the actor."""
    host = session.host if session.host and session.host != session.actor else ""
    short = session.host_session[-4:] if session.host_session else ""
    if host and short:
        return f" [dim]via {escape_markup(host)} · {escape_markup(short)}[/]"
    if short:
        return f" [dim]via {escape_markup(short)}[/]"
    if host:
        return f" [dim]via {escape_markup(host)}[/]"
    return ""


def session_line(
    session: Session,
    now: float | None = None,
    idle_after: float | None = None,
    plan_title: str = "",
) -> str:
    """One card row: identity, plan, task, branch, age, and live state."""
    stamp = time.time() if now is None else now
    state = services.session_state(session, stamp, idle_after)
    started = time.strftime("%H:%M", time.localtime(session.started_at))
    parts = [f"[dim]{escape_markup(plan_label(session, plan_title))}[/]"]
    task = task_label(session)
    if task:
        parts.append(task)
    parts.append(escape_markup(branch_label(session)))
    return (
        f"[bold]@{escape_markup(session.actor)}[/]{host_label(session)} "
        f"[dim]S{session.id}[/] · "
        + " · ".join(parts)
        + f" · [dim]{started} · {age(session.started_at, stamp)}[/] · "
        f"{STATE_BADGES.get(state, state)}"
    )


def sessions_summary(
    sessions: list[Session],
    now: float | None = None,
    idle_after: float | None = None,
) -> str:
    """Border subtitle counts: open, awaiting, and idle."""
    stamp = time.time() if now is None else now
    states = [services.session_state(session, stamp, idle_after) for session in sessions]
    parts = [f"{len(sessions)} open"]
    awaiting = states.count("awaiting")
    stale = states.count("stale")
    idle = states.count("idle")
    if awaiting:
        parts.append(f"{awaiting} awaiting")
    if stale:
        parts.append(f"{stale} stale")
    if idle:
        parts.append(f"{idle} idle")
    return " · ".join(parts)
