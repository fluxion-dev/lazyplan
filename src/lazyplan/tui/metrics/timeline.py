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
MIN_SPAN_SECONDS = 60.0
TRACE_GLYPHS = {"plan": "═", "milestone": "─", "task": "·"}
AXIS_FORMATS = (
    (10 * 60, "%H:%M:%S", 4),
    (2 * 86_400, "%H:%M", 5),
    (10 * 86_400, "%b %d %H:%M", 4),
    (120 * 86_400, "%b %d", 5),
    (float("inf"), "%b %Y", 5),
)


def _trace_glyph(kind: str) -> str:
    """Line glyph for one lane kind."""
    return TRACE_GLYPHS.get(kind, "─")


def _legend_entry(lane: TimelineLane) -> str:
    """One legend label with its kind glyph and truncated title."""
    return f"{_trace_glyph(lane.kind)} {truncate(lane.title, LEGEND_LABEL_WIDTH)}"


def _legend_layout(
    lanes: tuple[TimelineLane, ...], width: int, max_rows: int
) -> tuple[list[list[int]], int]:
    """Group lane indexes into horizontal legend rows, trimming overflow."""
    if not lanes or max_rows <= 0:
        return [], len(lanes)
    rows: list[list[int]] = []
    current: list[int] = []
    used = 0
    for index, lane in enumerate(lanes):
        entry_width = len(_legend_entry(lane)) + 2
        if current and used + entry_width > width:
            rows.append(current)
            current = []
            used = 0
        current.append(index)
        used += entry_width
    if current:
        rows.append(current)
    if len(rows) <= max_rows:
        return rows, 0
    rows = rows[:max_rows]
    hidden = len(lanes) - sum(len(row) for row in rows)
    while rows:
        last = rows[-1]
        overflow = f"+{hidden} more"
        last_width = sum(len(_legend_entry(lanes[index])) + 2 for index in last)
        if last_width + len(overflow) + 2 <= width:
            break
        if last:
            hidden += 1
            last.pop()
        else:
            break
    return rows, hidden


def _axis_ticks(left: float, right: float, span: float) -> tuple[list[float], list[str]]:
    """Tick positions and unique labels chosen from the timeline span."""
    for limit, fmt, count in AXIS_FORMATS:
        if span < limit:
            ticks = [left + (right - left) * index / (count - 1) for index in range(count)]
            labels = [datetime.fromtimestamp(stamp).strftime(fmt) for stamp in ticks]
            if len(set(labels)) == len(labels):
                return ticks, labels
    ticks = [left + (right - left) * index / 4 for index in range(5)]
    labels = [datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M:%S") for stamp in ticks]
    return ticks, labels


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
            self._draw_empty(plot, timeline.empty if timeline is not None else "")
            return
        self._draw(plot, timeline)

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
                    marker=_trace_glyph(lane.kind),
                    color=color,
                )
                plt.scatter(
                    [start, end],
                    [positions[index], positions[index]],
                    marker="dot",
                    color=color,
                )
        ticks, labels = _axis_ticks(left, right, span)
        rows = max(2, (plot.size.height or 12) - 3)
        width = max(20, (plot.size.width or 80) - 2)
        max_rows = max(1, min(MAX_LEGEND_ROWS, rows - 1))
        legend_data, hidden = _legend_layout(lanes, width, max_rows)
        legend_rows = len(legend_data)
        row_unit, top, bottom = _lane_window(rows, count, legend_rows)
        plt.xlim(left, right)
        plt.ylim(-0.5 - bottom, top)
        plt.xticks(ticks, labels)
        plt.yticks(positions, ["" for _ in positions])
        if any(lane.active and lane.active[-1][1] >= timeline.now for lane in lanes):
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
                text = _legend_entry(lane)
                plt.text(
                    text,
                    left + column * char_unit,
                    top - row_unit * (row_index + 0.5),
                    color=lane_rgb(self.app, index),
                    background=surface,
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
