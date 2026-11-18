"""Canonical labels and TUI row markup for plans, milestones, and tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....core.entities import Status
from ....core.kinds import LABEL_LETTERS, MILESTONE, PLAN, TASK
from .row_stats import RowStats, render_stats, stats_layout
from .status import cell_width, status_mark, status_state
from .text import _escape_markup, repo_project_name, status_word, truncate

if TYPE_CHECKING:
    from ....core.entities import Milestone, Plan, PlanDraft, Task
    from ....core.ports.insights import InsightsPort

    RepoMap = dict[tuple[str, int], list[dict]]

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


def _row_state(obj: Plan | Milestone | Task, attention: bool, review: bool = False) -> str:
    """One presentation state per row, never a trailing status word."""
    return status_state(
        obj.status,
        blocked=bool(getattr(obj, "blocked", False)),
        review=review,
        attention=attention,
    )


def _render_row(
    kind: str,
    obj: Plan | Milestone | Task,
    stats: RowStats,
    width: int | None,
    badge: str = "",
    *,
    attention: bool = False,
    review: bool = False,
    emoji: bool = True,
) -> str:
    """Render one TUI row: id, title, progress, and the right-rail mark."""
    _letter, title_attr = _CORE_SPEC[kind]
    id_part = f"{_letter}{obj.id}"
    title = getattr(obj, title_attr)
    if badge:
        title = f"{title} {badge}"
    mark = status_mark(_row_state(obj, attention, review), emoji=emoji)
    prefix_rich = f"[dim]{id_part}[/] "
    prefix_plain = f"{id_part} "
    row_width = DEFAULT_ROW_WIDTH if width is None else width
    layout = stats_layout(kind, row_width, cell_width(prefix_plain))
    stats = RowStats(progress=stats.progress, state=mark)
    stats_rich, stats_plain = render_stats(stats, layout)
    gap = 1 if layout else 0
    available = row_width - cell_width(prefix_plain) - cell_width(stats_plain) - gap
    title = truncate(title, max(0, available))
    pad = " " * max(
        gap,
        row_width - cell_width(prefix_plain) - cell_width(title) - cell_width(stats_plain),
    )
    style = "dim" if obj.status == Status.DONE else "bold"
    return f"{prefix_rich}[{style}]{_escape_markup(title)}[/]{pad}{stats_rich}"


def plan_label(
    p: Plan,
    store: InsightsPort | None = None,
    dot: str = "plain",
    repos: RepoMap | None = None,
) -> str:
    """Canonical row label for a plan (plain text: CLI, tests).

    Pass `repos` when labeling a list so one repo read serves every row.
    """
    base = _label("plan", p, store, dot)
    if store is None:
        return base
    linked = (
        repos.get(("plan", p.id), []) if repos is not None else store.effective_repos("plan", p.id)
    )
    names = [n for n in (repo_project_name(r) for r in linked) if n]
    return f"{base} [{', '.join(names)}]" if names else base


def plan_row(
    p: Plan,
    store: InsightsPort | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    attention: bool = False,
    worktrees: int = 0,
    *,
    review: bool = False,
    emoji: bool = True,
) -> str:
    """TUI plan row (Rich markup): one status mark, id, title, and count."""
    stats = RowStats(progress=progress)
    return _render_row(
        "plan",
        p,
        stats,
        width,
        badge="wt" if worktrees else "",
        attention=attention,
        review=review,
        emoji=emoji,
    )


def milestone_label(s: Milestone, store: InsightsPort | None = None, dot: str = "plain") -> str:
    """Canonical row label for a milestone."""
    return _label("milestone", s, store, dot)


def milestone_row(
    s: Milestone,
    store: InsightsPort | None = None,
    progress: tuple[int, int] | None = None,
    width: int | None = None,
    attention: bool = False,
    *,
    emoji: bool = True,
) -> str:
    """TUI milestone row (Rich markup): one status mark, id, title, and count."""
    stats = RowStats(progress=progress)
    return _render_row("milestone", s, stats, width, attention=attention, emoji=emoji)


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
    width: int | None = None,
    attention: bool = False,
    *,
    emoji: bool = True,
) -> str:
    """TUI task row (Rich markup): one status mark, id, and title."""
    stats = RowStats()
    return _render_row("task", t, stats, width, attention=attention, emoji=emoji)


def draft_label(draft: PlanDraft, open_count: int, total_count: int) -> str:
    """Canonical row label for a plan draft."""
    state = " revising" if draft.status == "revising" else ""
    target = f" -> P{draft.plan_id}" if draft.plan_id else ""
    return f"D{draft.id} {draft.title} {open_count}/{total_count}{state}{target}"


def draft_row(
    draft: PlanDraft,
    open_count: int,
    total_count: int,
    width: int | None = None,
    *,
    emoji: bool = True,
) -> str:
    """TUI draft row (Rich markup): id + title + open/total and revising."""
    prefix_rich = f"[dim]D{draft.id}[/] "
    prefix_plain = f"D{draft.id} "
    row_width = DEFAULT_ROW_WIDTH if width is None else width
    stats = RowStats(
        progress=(open_count, total_count),
        state="revising" if draft.status == "revising" else "",
    )
    layout = stats_layout("draft", row_width, len(prefix_plain))
    stats_rich, stats_plain = render_stats(stats, layout)
    available = row_width - len(prefix_plain) - len(stats_plain)
    title = truncate(draft.title, available)
    pad = " " * max(0, row_width - len(prefix_plain) - len(title) - len(stats_plain))
    style = "dim" if draft.status == "promoted" else "bold"
    return f"{prefix_rich}[{style}]{_escape_markup(title)}[/]{pad}{stats_rich}"
