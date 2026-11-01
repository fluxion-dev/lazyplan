"""Status card: a Plotext bar chart of lifecycle states and the blocked overlay."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual_plotext import PlotextPlot

from ...metrics import StatusBreakdown, status_bars
from ..theme import apply_chart_theme, chart_color
from .base import MetricCard


class StatusCard(MetricCard):
    """Task status distribution card."""

    def __init__(self) -> None:
        super().__init__("metric-status", "Task status", "no tasks yet")

    def compose(self) -> ComposeResult:
        yield Label(self.card_title, classes="metric-title")
        yield Static(self.empty, id=f"{self.id}-empty", classes="metric-empty")
        yield PlotextPlot(id=f"{self.id}-plot")

    def refresh_status(self, status: StatusBreakdown | None) -> None:
        """Plot *status*, or show the empty state when there are no tasks."""
        has_data = status is not None and status.total > 0
        self.query_one(f"#{self.id}-empty", Static).display = not has_data
        plot = self.query_one(f"#{self.id}-plot", PlotextPlot)
        plot.display = has_data
        if status is None or not has_data:
            return
        rows = status_bars(status)
        labels = [row.label for row in rows]
        values = [row.value for row in rows]
        peak = max(values)
        plt = plot.plt
        apply_chart_theme(plt, self.app)
        plt.clear_figure()
        plt.bar(
            labels,
            values,
            orientation="horizontal",
            color=chart_color(self.app),
        )
        plt.xlim(0, peak)
        plt.xticks([0, peak], ["0", str(peak)])
        plot.refresh()
