"""The bottom metrics section and its card slots."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.containers import Vertical

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...metrics import MetricsSnapshot
from .base import MetricCard
from .progress import ProgressCard
from .status import StatusCard

if _TEXTUAL_OK:

    class MetricsSection(Vertical):
        """Always-on bottom section that hosts the read-only metric cards."""

        def __init__(self) -> None:
            super().__init__(id="metrics", classes="metrics-section")

        def compose(self) -> ComposeResult:
            yield MetricCard("metric-heatmap", "Activity", "no completions yet")
            yield ProgressCard()
            yield StatusCard()

        def refresh_snapshot(self, snapshot: MetricsSnapshot) -> None:
            """Push one snapshot into the cards.

            Each card owns its body; the section never computes metrics.
            """
            self.query_one("#metric-progress", ProgressCard).refresh_progress(snapshot.progress)
            self.query_one("#metric-status", StatusCard).refresh_status(snapshot.status)
