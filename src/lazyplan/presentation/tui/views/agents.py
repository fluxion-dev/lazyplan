"""Agent-session rows for the agents card.

Pure formatting: no Textual imports, so the CLI and tests can reuse the
state words without a terminal.
"""

from __future__ import annotations

import time

from .... import services
from ....core.entities import Session
from ....core.policies.sessions import IDLE_AFTER_SECS
from ...shared.design import escape_markup

STATE_BADGES = {
    "working": "[green]▶ working[/]",
    "awaiting": "[yellow]◆ awaiting you[/]",
    "idle": "[dim]◌ idle[/]",
    "ended": "[dim]ended[/]",
    "auto-closed": "[dim]auto-closed[/]",
}
_STATE_ORDER = {"awaiting": 0, "working": 1, "idle": 2, "ended": 3, "auto-closed": 3}


def age(started_at: float, stamp: float) -> str:
    """Compact age: minutes until an hour, then hours and minutes."""
    minutes = int(max(0.0, stamp - started_at) / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


def rank_sessions(
    sessions: list[Session],
    now: float | None = None,
    idle_after: float = IDLE_AFTER_SECS,
) -> list[Session]:
    """Awaiting first, then working, then stale; newest first within a state."""
    stamp = time.time() if now is None else now

    def key(session: Session) -> tuple[int, float]:
        state = services.session_state(session, stamp, idle_after)
        return (_STATE_ORDER.get(state, 3), -session.started_at)

    return sorted(sessions, key=key)


def session_line(
    session: Session,
    now: float | None = None,
    idle_after: float = IDLE_AFTER_SECS,
) -> str:
    """One card row: identity, plan, branch, age, and live state."""
    stamp = time.time() if now is None else now
    state = services.session_state(session, stamp, idle_after)
    started = time.strftime("%H:%M", time.localtime(session.started_at))
    plan = f"P{session.plan_id}" if session.plan_id is not None else "no plan"
    branch = escape_markup(session.branch) if session.branch else "no branch"
    host = (
        f" [dim]via {escape_markup(session.host)}[/]"
        if session.host and session.host != session.actor
        else ""
    )
    return (
        f"[bold]@{escape_markup(session.actor)}[/]{host} [dim]S{session.id}[/] · "
        f"[dim]{plan}[/] · {branch} · [dim]{started} · {age(session.started_at, stamp)}[/] · "
        f"{STATE_BADGES.get(state, state)}"
    )


def sessions_summary(
    sessions: list[Session],
    now: float | None = None,
    idle_after: float = IDLE_AFTER_SECS,
) -> str:
    """Border subtitle counts: open, awaiting, and idle."""
    stamp = time.time() if now is None else now
    states = [services.session_state(session, stamp, idle_after) for session in sessions]
    parts = [f"{len(sessions)} open"]
    awaiting = states.count("awaiting")
    idle = states.count("idle")
    if awaiting:
        parts.append(f"{awaiting} awaiting")
    if idle:
        parts.append(f"{idle} idle")
    return " · ".join(parts)
