"""Activity card: a 12-week Plotext bar chart of daily completions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Label, Static
from textual_plotext import PlotextPlot

from ...metrics import DayActivity, activity_weeks
from ..theme import apply_chart_theme, chart_color
from .base import MetricCard


class ActivityCard(MetricCard):
    """Weekly completion chart card."""

    def __init__(self) -> None:
        super().__init__("metric-heatmap", "Daily activity", "no completions yet")

    def compose(self) -> ComposeResult:
        yield Label(self.card_title, classes="metric-title")
        yield Static(self.empty, id=f"{self.id}-empty", classes="metric-empty")
        yield PlotextPlot(id=f"{self.id}-plot")

    def refresh_activity(self, activity: tuple[DayActivity, ...]) -> None:
        """Plot *activity*, or show the empty state when nothing completed."""
        rows = activity_weeks(activity)
        has_data = bool(rows) and any(row.value > 0 for row in rows)
        self.query_one(f"#{self.id}-empty", Static).display = not has_data
        plot = self.query_one(f"#{self.id}-plot", PlotextPlot)
        plot.display = has_data
        if not has_data:
            return
        labels = [row.label for row in rows]
        values = [row.value for row in rows]
        plt = plot.plt
        apply_chart_theme(plt, self.app)
        plt.clear_figure()
        plt.bar(labels, values, color=chart_color(self.app))
        step = max(1, len(labels) // 5)
        ticks = list(range(0, len(labels), step))
        if ticks[-1] != len(labels) - 1:
            ticks.append(len(labels) - 1)
        plt.xticks([float(index) for index in ticks], [labels[index] for index in ticks])
        peak = max(values)
        plt.ylim(0, peak)
        plt.yticks([0, peak], ["0", str(peak)])
        plot.refresh()
