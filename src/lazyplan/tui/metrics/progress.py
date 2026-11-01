"""Progress card: headline plus a Plotext milestone bar chart."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual_plotext import PlotextPlot

from ...design import escape_markup, truncate
from ...metrics import OverallProgress, milestone_bars
from ..theme import apply_chart_theme, chart_color
from .base import MetricCard

TITLE_WIDTH = 16


def _elapsed_text(seconds: float | None) -> str:
    """Compact elapsed time: 12d, 5h, or 40m."""
    if seconds is None:
        return "—"
    if seconds >= 86_400:
        return f"{int(seconds // 86_400)}d"
    if seconds >= 3_600:
        return f"{int(seconds // 3_600)}h"
    return f"{int(seconds // 60)}m"


def _headline(progress: OverallProgress) -> str:
    head = f"{progress.percent}% {progress.done}/{progress.total}"
    if progress.complete:
        return head + "\ncomplete"
    eta = progress.eta_date.isoformat() if progress.eta_date is not None else "—"
    return f"{head}\n{_elapsed_text(progress.elapsed_seconds)} · ETA {eta}"


class ProgressCard(MetricCard):
    """Overall completion and milestone progress card."""

    def __init__(self) -> None:
        super().__init__("metric-progress", "Project progress", "no plans yet")

    def compose(self) -> ComposeResult:
        yield Label(self.card_title, classes="metric-title")
        yield Static(self.empty, id=f"{self.id}-empty", classes="metric-empty")
        yield Static("", id=f"{self.id}-head", classes="metric-head")
        yield PlotextPlot(id=f"{self.id}-plot")

    def refresh_progress(self, progress: OverallProgress | None, scoped: bool = False) -> None:
        """Render *progress*, or the empty state when there is no work."""
        head = self.query_one(f"#{self.id}-head", Static)
        plot = self.query_one(f"#{self.id}-plot", PlotextPlot)
        empty = self.query_one(f"#{self.id}-empty", Static)
        if progress is None or progress.total <= 0:
            empty.update("no tasks in this plan" if scoped else self.empty)
            empty.display = True
            head.display = False
            head.update("")
            plot.display = False
            return
        rows = milestone_bars(progress)
        empty.display = False
        head.display = True
        head.update(_headline(progress))
        plot.display = bool(rows)
        if not rows:
            return
        labels = [truncate(escape_markup(row.label), TITLE_WIDTH) for row in rows]
        values = [row.value for row in rows]
        plt = plot.plt
        apply_chart_theme(plt, self.app)
        plt.clear_figure()
        plt.bar(
            labels,
            values,
            orientation="horizontal",
            color=chart_color(self.app),
        )
        plt.xlim(0, 100)
        plt.xticks([0, 50, 100], ["0%", "50%", "100%"])
        plot.refresh()
