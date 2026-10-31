"""Activity card: a 12-week grid of daily task completions."""

from __future__ import annotations

from ...design import HEATMAP_CELL, HEATMAP_EMPTY, HEATMAP_SHADES, heatmap_color
from ...metrics import DayActivity
from .base import MetricCard

COLUMNS = 12
ROWS = 7


def render_heatmap(activity: tuple[DayActivity, ...]) -> str:
    """Render the week grid plus the range/legend line."""
    if not activity or sum(day.done for day in activity) == 0:
        return ""
    peak = max(day.done for day in activity)
    lines: list[str] = []
    for row in range(ROWS):
        cells: list[str] = []
        for column in range(COLUMNS):
            index = column * ROWS + row
            if index >= len(activity):
                cells.append(" ")
                continue
            color = heatmap_color(activity[index].done, peak)
            cells.append(f"[{color}]{HEATMAP_CELL}[/]")
        lines.append(" ".join(cells))
    first = activity[0].day.strftime("%m-%d")
    last = activity[-1].day.strftime("%m-%d")
    legend = f"{first}→{last} less "
    for token in (HEATMAP_EMPTY, *HEATMAP_SHADES):
        legend += f"[{token}]{HEATMAP_CELL}[/]"
    lines.append(legend + " more")
    return "\n".join(lines)


class HeatmapCard(MetricCard):
    """Daily completion heatmap card."""

    def __init__(self) -> None:
        super().__init__("metric-heatmap", "Daily activity", "no completions yet")

    def refresh_activity(self, activity: tuple[DayActivity, ...]) -> None:
        """Render *activity*, or the empty state when nothing completed."""
        if not activity or sum(day.done for day in activity) == 0:
            self.show_empty()
            return
        self.show(render_heatmap(activity))
