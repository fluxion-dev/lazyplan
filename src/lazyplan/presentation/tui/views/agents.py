"""Exact agent rows for the tracker.

Pure formatting: no Textual imports, so the CLI and tests can reuse the
status words without a terminal. The registry is authoritative; nothing here
infers a state from elapsed time.
"""

from __future__ import annotations

import time
from typing import NamedTuple

from ....core.entities import Agent, Status
from ...shared.design import escape_markup, spinner_glyph, status_word, truncate

GLYPH_WAITING = "◆"
GLYPH_LOST = "✕"
GLYPH_BLOCKED = "⊘"
GLYPH_TOOL = "▶"
PLAN_SHARE = 0.45
MIN_PLAN_TITLE = 8
MIN_BRANCH = 10

_STATE_ORDER = {
    "waiting": 0,
    "working": 1,
    "tool": 1,
    "compacting": 1,
    "starting": 1,
    "blocked": 2,
    "lost": 3,
    "ended": 4,
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


def rank_agents(agents: list[Agent], now: float | None = None) -> list[Agent]:
    """Waiting first, then working, blocked, and lost; newest first within a state."""
    del now

    def key(agent: Agent) -> tuple[int, float]:
        return (_STATE_ORDER.get(agent.status, 3), -agent.started_at)

    return sorted(agents, key=key)


def agent_id(agent: Agent) -> str:
    """Short human id: ``A12``."""
    return f"A{agent.id}"


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
    """A spinner while active, then a distinct glyph per terminal state."""
    if state in ("working", "starting", "compacting", "tool"):
        if state == "tool":
            return GLYPH_TOOL
        return status_word(Status.DOING) if frame is None else spinner_glyph(frame)
    if state == "waiting":
        return GLYPH_WAITING
    if state == "lost":
        return GLYPH_LOST
    if state == "blocked":
        return GLYPH_BLOCKED
    return GLYPH_LOST


def _glyph_markup(state: str, glyph: str) -> str:
    color = {
        "working": "green",
        "starting": "green",
        "tool": "cyan",
        "compacting": "cyan",
        "waiting": "yellow",
        "blocked": "yellow",
        "lost": "red",
        "ended": "dim",
    }.get(state, "dim")
    return f"[{color}]{glyph}[/]"


def _fixed_cells(
    agent: Agent,
    short_id: str,
    plan_head: str,
    age_text: str,
    glyph: str,
) -> int:
    """Cells the row spends before the plan title and branch share the rest."""
    head = len(f"@{agent.agent} {short_id} · {plan_head}")
    plan_space = 1 if agent.plan_id is not None else 0
    separators = len(" · ") * 4
    return head + plan_space + separators + len(age_text) + len(glyph)


def row_widths(
    agent: Agent,
    width: int | None,
    short_id: str,
    plan_head: str,
    age_text: str,
    glyph: str,
) -> RowWidths | None:
    """Width budget for one row, or None when the caller gave no width."""
    if width is None:
        return None
    fixed = _fixed_cells(agent, short_id, plan_head, age_text, glyph)
    return _share_widths(width - fixed, agent.plan_id is not None)


def agent_line(
    agent: Agent,
    now: float | None = None,
    plan_title: str = "",
    width: int | None = None,
    frame: int | None = 0,
) -> str:
    """One live row: agent, id, plan/task, branch, age, and status glyph."""
    stamp = time.time() if now is None else now
    state = agent.status
    short_id = agent_id(agent)
    task = f" T{agent.task_id}" if agent.task_id is not None else ""
    plan_head = f"P{agent.plan_id}" if agent.plan_id is not None else "unbound"
    age_text = age(agent.started_at, stamp)
    glyph = state_glyph(state, frame)
    widths = row_widths(agent, width, short_id, plan_head, age_text, glyph)
    title = plan_title if widths is None else truncate(plan_title, widths.title)
    branch = agent.branch or "-"
    if widths is not None:
        branch = truncate(branch, widths.branch)

    plan = f"[dim]{plan_head}[/]"
    if title:
        plan += f" {escape_markup(title)}"
    if task:
        plan += f"[dim]{task}[/]"
    marker = ""
    if agent.unbound:
        marker = " [yellow]unbound[/]"
    return (
        f"[bold]@{escape_markup(agent.agent)}[/] [dim]{escape_markup(short_id)}[/] · "
        f"{plan} · {escape_markup(branch)} · [dim]{age_text}[/] · "
        f"{_glyph_markup(state, glyph)} [dim]{escape_markup(state)}[/]{marker}"
    )


def agents_summary(agents: list[Agent], now: float | None = None) -> str:
    """Border subtitle counts: open, waiting, lost, and unbound."""
    del now
    parts = [f"{len(agents)} open"]
    for state in ("waiting", "lost", "blocked"):
        count = sum(1 for agent in agents if agent.status == state)
        if count:
            parts.append(f"{count} {state}")
    unbound = sum(1 for agent in agents if agent.unbound)
    if unbound:
        parts.append(f"{unbound} unbound")
    return " · ".join(parts)
