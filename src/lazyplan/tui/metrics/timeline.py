"""Timeline card: wall-clock swimlanes for the project and its milestones."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual_plotext import PlotextPlot

from ...design import truncate
from ...metrics import Timeline, TimelineLane
from ..theme import apply_chart_theme, chart_color, lane_rgb, token_rgb
from .base import MetricCard

LEGEND_LABEL_WIDTH = 16
MAX_LEGEND_ROWS = 6
X_TICKS = 5
MIN_SPAN_SECONDS = 60.0


def _tick_label(stamp: float, span: float) -> str:
    """Compact wall-clock label for one x-axis tick."""
    moment = datetime.fromtimestamp(stamp)
    if span < 2 * 86_400:
        return moment.strftime("%H:%M")
    if span < 60 * 86_400:
        return moment.strftime("%b %d")
    return moment.strftime("%Y-%m-%d")


def _active_segments(
    lane: TimelineLane, left: float, right: float, min_visible: float
) -> list[tuple[float, float]]:
    """Visible trace segments for one lane's doing intervals."""
    segments: list[tuple[float, float]] = []
    for start, end in lane.active:
        if end < left or start > right:
            continue
        start = max(start, left)
        end = min(right, max(end, start + min_visible))
        segments.append((start, end))
    return segments


def _lane_window(rows: int, count: int, legend_rows: int) -> tuple[float, float, float]:
    """Y scale, top, and spare bottom rows for one-row lane spacing."""
    content = count + legend_rows
    if content <= rows:
        return 1.0, count - 0.5 + legend_rows, float(rows - content)
    unit = content / rows
    return unit, count - 0.5 + legend_rows * unit, 0.0


class TimelineCard(MetricCard):
    """One swimlane per project or milestone from its start to its finish."""

    def __init__(self) -> None:
        super().__init__("metric-timeline", "no plans yet")

    def compose(self) -> ComposeResult:
        yield PlotextPlot(id=f"{self.id}-plot")

    def refresh_timeline(self, timeline: Timeline | None) -> None:
        """Render the wall-clock lanes, or the empty state when there are none."""
        plot = self.query_one(f"#{self.id}-plot", PlotextPlot)
        lanes = timeline.lanes if timeline is not None else ()
        if timeline is None or not lanes:
            self._draw_empty(plot)
            return
        self._draw(plot, timeline)

    def _draw_empty(self, plot: PlotextPlot) -> None:
        """Centered empty copy drawn by Plotext, with no axes or ticks."""
        plt = plot.plt
        plt.clear_figure()
        plt.frame(False)
        plt.xaxes(False, False)
        plt.yaxes(False, False)
        plt.xticks([], [])
        plt.yticks([], [])
        plt.text(
            self.empty,
            0.5,
            0.5,
            color=chart_color(self.app, "lp-chart-label"),
            alignment="center",
        )
        plot.refresh()

    def _draw(self, plot: PlotextPlot, timeline: Timeline) -> None:
        """Plot one braille line per lane with a legend overlaid at top left."""
        lanes = timeline.lanes
        count = len(lanes)
        positions = [float(count - 1 - index) for index in range(count)]
        span = max(timeline.end - timeline.start, MIN_SPAN_SECONDS)
        pad = max(MIN_SPAN_SECONDS, span * 0.02)
        left, right = timeline.start - pad, timeline.end + pad
        min_visible = max(1.0, span * 0.005)
        surface = token_rgb(self.app, "lp-surface")
        plt = plot.plt
        apply_chart_theme(plt, self.app)
        plt.clear_figure()
        for index, lane in enumerate(lanes):
            color = lane_rgb(self.app, index)
            for start, end in _active_segments(lane, left, right, min_visible):
                plt.plot(
                    [start, end],
                    [positions[index], positions[index]],
                    marker="braille",
                    color=color,
                )
                plt.scatter(
                    [start, end],
                    [positions[index], positions[index]],
                    marker="dot",
                    color=color,
                )
        ticks = [left + (right - left) * index / (X_TICKS - 1) for index in range(X_TICKS)]
        rows = max(2, (plot.size.height or 12) - 3)
        legend_rows = min(count, MAX_LEGEND_ROWS, max(1, rows - 1))
        row_unit, top, bottom = _lane_window(rows, count, legend_rows)
        plt.xlim(left, right)
        plt.ylim(-0.5 - bottom, top)
        plt.xticks(ticks, [_tick_label(stamp, span) for stamp in ticks])
        plt.yticks(positions, ["" for _ in positions])
        self._legend(plt, lanes, left, top, row_unit, legend_rows, surface)
        plot.refresh()

    def _legend(
        self,
        plt: Any,
        lanes: tuple[TimelineLane, ...],
        left: float,
        top: float,
        row_unit: float,
        legend_rows: int,
        surface: tuple[int, int, int],
    ) -> None:
        """Stack colour-keyed labels in the chart's top-left corner."""
        shown = min(len(lanes), legend_rows)
        if shown < len(lanes) and legend_rows >= 2:
            shown -= 1
        for index in range(shown):
            lane = lanes[index]
            plt.text(
                f"⠒ {truncate(lane.title, LEGEND_LABEL_WIDTH)}",
                left,
                top - row_unit * (index + 0.5),
                color=lane_rgb(self.app, index),
                background=surface,
                alignment="left",
            )
        if shown < len(lanes):
            plt.text(
                f"+{len(lanes) - shown} more",
                left,
                top - row_unit * (shown + 0.5),
                color=token_rgb(self.app, "lp-chart-label"),
                background=surface,
                alignment="left",
            )
