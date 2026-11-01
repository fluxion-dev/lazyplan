"""Pure layout helpers for the Gantt timeline card."""

from __future__ import annotations

from datetime import datetime

from ...design import truncate
from ...metrics import TimelineLane

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


def trace_glyph(kind: str) -> str:
    """Line glyph for one lane kind."""
    return TRACE_GLYPHS.get(kind, "─")


def legend_entry(lane: TimelineLane) -> str:
    """One legend label with its kind glyph and truncated title."""
    suffix = " *" if lane.selected else ""
    return f"{trace_glyph(lane.kind)} {truncate(lane.title, LEGEND_LABEL_WIDTH)}{suffix}"


def legend_layout(
    lanes: tuple[TimelineLane, ...], width: int, max_rows: int
) -> tuple[list[list[int]], int]:
    """Group lane indexes into horizontal legend rows, trimming overflow."""
    if not lanes or max_rows <= 0:
        return [], len(lanes)
    rows: list[list[int]] = []
    current: list[int] = []
    used = 0
    for index, lane in enumerate(lanes):
        entry_width = len(legend_entry(lane)) + 2
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
        last_width = sum(len(legend_entry(lanes[index])) + 2 for index in last)
        if last_width + len(overflow) + 2 <= width:
            break
        if last:
            hidden += 1
            last.pop()
        else:
            break
    return rows, hidden


def axis_ticks(left: float, right: float, span: float) -> tuple[list[float], list[str]]:
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


def active_segments(
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


def lane_window(rows: int, count: int, legend_rows: int) -> tuple[float, float, float]:
    """Y scale, top, and spare bottom rows for one-row lane spacing."""
    content = count + legend_rows
    if content <= rows:
        return 1.0, count - 0.5 + legend_rows, float(rows - content)
    unit = content / rows
    return unit, count - 0.5 + legend_rows * unit, 0.0
