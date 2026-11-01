"""Timeline card: wall-clock swimlanes for the project and its milestones."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual_plotext import PlotextPlot

from ...metrics import Timeline, TimelineLane
from ..query import query_one_opt
from ..theme import (
    apply_chart_theme,
    chart_color,
    lane_baseline_rgb,
    lane_rgb,
    token_rgb,
)
from .base import MetricCard
from .timeline_layout import (
    MAX_LEGEND_ROWS,
    MIN_SPAN_SECONDS,
    axis_ticks,
    lane_window,
    legend_entry,
    legend_layout,
    trace_glyph,
    trace_points,
    trace_segments,
)


class TimelineCard(MetricCard):
    """One swimlane per project or milestone from its start to its finish."""

    def __init__(self) -> None:
        super().__init__("metric-timeline", "no plans yet")

    def compose(self) -> ComposeResult:
        with VerticalScroll(id=f"{self.id}-scroll"):
            yield PlotextPlot(id=f"{self.id}-plot")

    def refresh_timeline(self, timeline: Timeline | None) -> None:
        """Render the wall-clock lanes, or the empty state when there are none."""
        plot = query_one_opt(self, f"#{self.id}-plot", PlotextPlot)
        scroll = query_one_opt(self, f"#{self.id}-scroll", VerticalScroll)
        if plot is None:
            return
        lanes = timeline.lanes if timeline is not None else ()
        if timeline is None or not lanes:
            plot.styles.height = max(1, scroll.size.height if scroll is not None else 12)
            self._draw_empty(plot, timeline.empty if timeline is not None else "")
            return
        width = max(20, ((scroll.size.width if scroll is not None else plot.size.width) or 80) - 2)
        available = max(
            2, ((scroll.size.height if scroll is not None else plot.size.height) or 12) - 3
        )
        max_rows = max(1, min(MAX_LEGEND_ROWS, available - 1))
        legend_data, hidden = legend_layout(lanes, width, max_rows)
        rows = max(available, len(legend_data) + len(lanes))
        plot.styles.height = rows + 3
        self._draw(plot, timeline, rows, width, legend_data, hidden)

    def _draw_empty(self, plot: PlotextPlot, reason: str = "") -> None:
        """Centered empty copy drawn by Plotext, with no axes or ticks."""
        plt = plot.plt
        plt.clear_figure()
        plt.frame(False)
        plt.xaxes(False, False)
        plt.yaxes(False, False)
        plt.xticks([], [])
        plt.yticks([], [])
        plt.text(
            reason or self.empty,
            0.5,
            0.5,
            color=chart_color(self.app, "lp-chart-label"),
            alignment="center",
        )
        plot.refresh()

    def _draw(
        self,
        plot: PlotextPlot,
        timeline: Timeline,
        rows: int,
        width: int,
        legend_data: list[list[int]],
        hidden: int,
    ) -> None:
        """Plot one glyph line per lane with a legend overlaid at the top."""
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
            y = positions[index]
            self._draw_baseline(plt, index, y, left, right)
            self._draw_trace(plt, lane, y, color, left, right, min_visible, width)
        ticks, labels = axis_ticks(left, right, span)
        legend_rows = len(legend_data)
        row_unit, top, bottom = lane_window(rows, count, legend_rows)
        plt.xlim(left, right)
        plt.ylim(-0.5 - bottom, top)
        plt.xticks(ticks, labels)
        plt.yticks(positions, ["" for _ in positions])
        if any(lane.end >= timeline.now for lane in lanes):
            axis = token_rgb(self.app, "lp-chart-axis")
            plt.vline(timeline.end, color=axis)
            plt.text(
                "now",
                timeline.end,
                top - 0.5,
                color=axis,
                background=surface,
                alignment="center",
            )
        self._legend(
            plt,
            lanes,
            legend_data,
            hidden,
            left,
            right,
            top,
            row_unit,
            width,
            surface,
        )
        plot.refresh()

    def _draw_baseline(
        self,
        plt: Any,
        index: int,
        y: float,
        left: float,
        right: float,
    ) -> None:
        """Draw the dim full-width baseline for one lane."""
        plt.plot(
            [left, right],
            [y, y],
            marker="─",
            color=lane_baseline_rgb(self.app, index),
        )

    def _draw_trace(
        self,
        plt: Any,
        lane: TimelineLane,
        y: float,
        color: tuple[int, int, int],
        left: float,
        right: float,
        min_visible: float,
        width: int,
    ) -> None:
        """Draw one lane's rendered trace segments, bold when selected."""
        for start, end in trace_segments(lane, left, right, min_visible):
            if lane.selected:
                points = trace_points(start, end, left, right, width)
                plt.scatter(
                    points,
                    [y] * len(points),
                    marker=trace_glyph(lane.kind, bold=True),
                    color=color,
                    style="bold",
                )
                plt.scatter(
                    [start, end],
                    [y, y],
                    marker=trace_glyph(lane.kind),
                    color=color,
                    style="bold",
                )
                continue
            plt.plot(
                [start, end],
                [y, y],
                marker=trace_glyph(lane.kind),
                color=color,
            )
            plt.scatter(
                [start, end],
                [y, y],
                marker="dot",
                color=color,
            )

    def _legend(
        self,
        plt: Any,
        lanes: tuple[TimelineLane, ...],
        rows: list[list[int]],
        hidden: int,
        left: float,
        right: float,
        top: float,
        row_unit: float,
        width: int,
        surface: tuple[int, int, int],
    ) -> None:
        """Draw a horizontal colour-keyed legend across the chart's top rows."""
        char_unit = (right - left) / max(1, width)
        for row_index, row in enumerate(rows):
            column = 0
            for index in row:
                lane = lanes[index]
                text = legend_entry(lane)
                plt.text(
                    text,
                    left + column * char_unit,
                    top - row_unit * (row_index + 0.5),
                    color=lane_rgb(self.app, index),
                    background=surface,
                    style="bold" if lane.selected else None,
                    alignment="left",
                )
                column += len(text) + 2
            if hidden and row_index == len(rows) - 1:
                plt.text(
                    f"+{hidden} more",
                    left + column * char_unit,
                    top - row_unit * (row_index + 0.5),
                    color=token_rgb(self.app, "lp-chart-label"),
                    background=surface,
                    alignment="left",
                )
