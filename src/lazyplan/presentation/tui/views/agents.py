"""Agent-session rows for the agents card.

Pure formatting: no Textual imports, so the CLI and tests can reuse the
state words without a terminal.
"""

from __future__ import annotations

import time
from typing import NamedTuple

from .... import services
from ....core.entities import Session, Status
from ...shared.design import escape_markup, spinner_glyph, status_word, truncate

GLYPH_AWAITING = "◆"
GLYPH_QUIET = "◌"
PLAN_SHARE = 0.45
MIN_PLAN_TITLE = 8
MIN_BRANCH = 10

_STATE_ORDER = {
    "awaiting": 0,
    "working": 1,
    "stale": 2,
    "idle": 3,
    "ended": 4,
    "auto-closed": 4,
}


class RowWidths(NamedTuple):
    """Plan-title and branch cells left after the fixed columns."""

    title: int
    branch: int


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


def agent_id(session: Session) -> str:
    """Last four characters of the host session, or ``-`` for manual rows."""
    return session.host_session[-4:] if session.host_session else "-"


def _share_widths(available: int, has_plan: bool) -> RowWidths:
    """Plan-title and branch cells: 45/55, with minimums, never over budget."""
    budget = max(available, 0)
    if not has_plan:
        return RowWidths(0, budget)
    if budget >= MIN_PLAN_TITLE + MIN_BRANCH:
        title = max(MIN_PLAN_TITLE, int(budget * PLAN_SHARE))
        branch = budget - title
        if branch < MIN_BRANCH:
            branch = MIN_BRANCH
            title = budget - branch
        return RowWidths(title, branch)
    title = int(budget * PLAN_SHARE)
    return RowWidths(title, budget - title)


def state_glyph(state: str, frame: int | None) -> str:
    """A spinner frame while working, ``◆`` awaiting, ``◌`` for quiet rows."""
    if state == "working":
        return status_word(Status.DOING) if frame is None else spinner_glyph(frame)
    if state == "awaiting":
        return GLYPH_AWAITING
    return GLYPH_QUIET


def _glyph_markup(state: str, glyph: str) -> str:
    color = {"working": "green", "awaiting": "yellow", "stale": "yellow"}.get(state, "dim")
    return f"[{color}]{glyph}[/]"


def _fixed_cells(
    session: Session,
    short_id: str,
    plan_head: str,
    age_text: str,
    glyph: str,
) -> int:
    """Cells the row spends before the plan title and branch share the rest."""
    head = len(f"@{session.actor} {short_id} · {plan_head}")
    plan_space = 1 if session.plan_id is not None else 0
    separators = len(" · ") * 3
    return head + plan_space + separators + len(age_text) + len(glyph)


def row_widths(
    session: Session,
    width: int | None,
    short_id: str,
    plan_head: str,
    age_text: str,
    glyph: str,
) -> RowWidths | None:
    """Width budget for one row, or None when the caller gave no width."""
    if width is None:
        return None
    fixed = _fixed_cells(session, short_id, plan_head, age_text, glyph)
    return _share_widths(width - fixed, session.plan_id is not None)


def session_line(
    session: Session,
    now: float | None = None,
    idle_after: float | None = None,
    plan_title: str = "",
    width: int | None = None,
    frame: int | None = 0,
) -> str:
    """One live row: agent, agent id, plan, branch, age, and state glyph."""
    stamp = time.time() if now is None else now
    state = services.session_state(session, stamp, idle_after)
    short_id = agent_id(session)
    plan_head = f"P{session.plan_id}" if session.plan_id is not None else "-"
    age_text = age(session.started_at, stamp)
    glyph = state_glyph(state, frame)
    widths = row_widths(session, width, short_id, plan_head, age_text, glyph)
    title = plan_title if widths is None else truncate(plan_title, widths.title)
    branch = session.branch or "-"
    if widths is not None:
        branch = truncate(branch, widths.branch)

    plan = f"[dim]{plan_head}[/]"
    if title:
        plan += f" {escape_markup(title)}"
    return (
        f"[bold]@{escape_markup(session.actor)}[/] [dim]{escape_markup(short_id)}[/] · "
        f"{plan} · {escape_markup(branch)} · [dim]{age_text}[/] · "
        f"{_glyph_markup(state, glyph)}"
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
