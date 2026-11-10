"""Canonical labels and TUI row markup for plans, milestones, and tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....core.entities import Status
from ....core.kinds import LABEL_LETTERS, MILESTONE, PLAN, TASK
from .row_stats import RowStats, render_stats, stats_layout
from .text import _escape_markup, repo_project_name, status_prefix, status_word, truncate

if TYPE_CHECKING:
    from ....core.entities import Milestone, Plan, Task
    from ....core.ports.insights import InsightsPort

DEFAULT_ROW_WIDTH = 80

_CORE_SPEC: dict[str, tuple[str, str]] = {
    PLAN: (LABEL_LETTERS[PLAN], "name"),
    MILESTONE: (LABEL_LETTERS[MILESTONE], "title"),
    TASK: (LABEL_LETTERS[TASK], "title"),
}


def _core(kind: str, obj: Plan | Milestone | Task, store: InsightsPort | None) -> str:
    """Label body without the leading status word, shared by label and row."""
    letter, title_attr = _CORE_SPEC[kind]
    title = getattr(obj, title_attr)
    return f"{letter}{obj.id} {title}"


def _label(kind: str, obj: Plan | Milestone | Task, store: InsightsPort | None, dot: str) -> str:
    """Canonical row label: status word + body (plain text: CLI, tests)."""
    return f"{status_word(obj.status, dot)} {_core(kind, obj, store)}"


def _render_row(
    kind: str,
    obj: Plan | Milestone | Task,
    stats: RowStats,
    width: int | None,
) -> str:
    """Render one TUI row from the fixed stat slots."""
    _letter, title_attr = _CORE_SPEC[kind]
    id_part = f"{LABEL_LETTERS[kind]}{obj.id}"
    title = getattr(obj, title_attr)
    prefix_rich = f"{status_prefix(obj.status)} [dim]{id_part}[/] "
    prefix_plain = f"{status_word(obj.status)} {id_part} "
    row_width = DEFAULT_ROW_WIDTH if width is None else width
    layout = stats_layout(kind, row_width, len(prefix_plain))
    stats_rich, stats_plain = render_stats(stats, layout)
    available = row_width - len(prefix_plain) - len(stats_plain)
    title = truncate(title, available)
    pad = " " * max(0, row_width - len(prefix_plain) - len(title) - len(stats_plain))
    style = "dim" if obj.status == Status.DONE else "bold"
    return f"{prefix_rich}[{style}]{_escape_markup(title)}[/]{pad}{stats_rich}"


def plan_label(p: Plan, store: InsightsPort | None = None, dot: str = "plain") -> str:
    """Canonical row label for a plan (plain text: CLI, tests)."""
    base = _label("plan", p, store, dot)
    if store is None:
        return base
    names = [n for n in (repo_project_name(r) for r in store.effective_repos("plan", p.id)) if n]
    return f"{base} [{', '.join(names)}]" if names else base


def plan_row(
    p: Plan,
    store: InsightsPort | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    attention: bool = False,
) -> str:
    """TUI plan row (Rich markup): glyph + id + title + progress + attention."""
    stats = RowStats(kind="plan", progress=progress, attention=attention)
    return _render_row("plan", p, stats, width)


def milestone_label(s: Milestone, store: InsightsPort | None = None, dot: str = "plain") -> str:
    """Canonical row label for a milestone."""
    return _label("milestone", s, store, dot)


def milestone_row(
    s: Milestone,
    store: InsightsPort | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    attention: bool = False,
) -> str:
    """TUI milestone row (Rich markup): glyph + id + title + progress + attention."""
    stats = RowStats(kind="milestone", progress=progress, attention=attention)
    return _render_row("milestone", s, stats, width)


def task_label(t: Task, store: InsightsPort | None = None, dot: str = "plain") -> str:
    """Canonical row label for a task, including blocked state and claim holder."""
    base = _label("task", t, store, dot)
    if t.blocked:
        base += " [blocked]"
    if store is None:
        return base
    claim = store.get_claim(t.id)
    return f"{base} @{claim.actor}" if claim is not None else base


def task_row(
    t: Task,
    store: InsightsPort | None = None,
    width: int | None = None,
    attention: bool = False,
    claim_actor: str = "",
    claim_expired: bool = False,
    blocked: bool = False,
) -> str:
    """TUI task row (Rich markup): glyph + id + title + attention + claim."""
    stats = RowStats(
        kind="task",
        attention=attention,
        blocked=blocked,
        claim_actor=claim_actor,
        claim_expired=claim_expired,
    )
    return _render_row("task", t, stats, width)
