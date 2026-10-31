"""Progress card: overall completion, milestone bars, elapsed, and ETA."""

from __future__ import annotations

from ...design import escape_markup, metric_bar, truncate
from ...metrics import OverallProgress
from .base import MetricCard

TITLE_WIDTH = 20


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
        return head + " · complete"
    eta = progress.eta_date.isoformat() if progress.eta_date is not None else "—"
    return f"{head} · {_elapsed_text(progress.elapsed_seconds)} · ETA {eta}"


def render_progress(progress: OverallProgress | None) -> str:
    """Render the card body; the caller handles the empty state."""
    if progress is None or progress.total <= 0:
        return ""
    lines = [_headline(progress)]
    for item in progress.milestones:
        label = truncate(escape_markup(item.title), TITLE_WIDTH)
        lines.append(f"{metric_bar(item.done, item.total)} {item.done}/{item.total} {label}")
    return "\n".join(lines)


class ProgressCard(MetricCard):
    """Overall completion and forecast card."""

    def __init__(self) -> None:
        super().__init__("metric-progress", "Progress", "no plans yet")

    def refresh_progress(self, progress: OverallProgress | None) -> None:
        """Render *progress*, or the empty state when there is no work."""
        if progress is None or progress.total <= 0:
            self.show_empty()
            return
        self.show(render_progress(progress))
