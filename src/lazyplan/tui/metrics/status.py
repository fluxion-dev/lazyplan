"""Status card: lifecycle counts, shares, and the blocked overlay."""

from __future__ import annotations

from ...design import BLOCKED_RICH, STATUS_RICH, metric_bar
from ...metrics import StatusBreakdown
from .base import MetricCard

ROWS = ("todo", "doing", "done", "blocked")


def _color(row: str) -> str:
    return BLOCKED_RICH if row == "blocked" else STATUS_RICH[row]


def render_status(status: StatusBreakdown | None) -> str:
    """Render the four rows; the caller handles the empty state."""
    if status is None or status.total <= 0:
        return ""
    counts = {
        "todo": status.todo,
        "doing": status.doing,
        "done": status.done,
        "blocked": status.blocked,
    }
    peak = max(counts.values())
    lines = []
    for row in ROWS:
        count = counts[row]
        share = status.share(count)
        lines.append(f"[{_color(row)}]{row:<7}[/] {metric_bar(count, peak)} {count:>2} {share:>3}%")
    return "\n".join(lines)


class StatusCard(MetricCard):
    """Task status distribution card."""

    def __init__(self) -> None:
        super().__init__("metric-status", "Status", "no tasks yet")

    def refresh_status(self, status: StatusBreakdown | None) -> None:
        """Render *status*, or the empty state when there are no tasks."""
        if status is None or status.total <= 0:
            self.show_empty()
            return
        self.show(render_status(status))
