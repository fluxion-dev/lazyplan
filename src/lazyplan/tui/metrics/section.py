"""The bottom metrics section and its card slots."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...design import escape_markup, truncate
from ...metrics import MetricsSnapshot
from .activity import ActivityCard
from .progress import ProgressCard
from .status import StatusCard

__all__ = ["MetricsSection"]

SCOPE_TITLE_WIDTH = 48

if _TEXTUAL_OK:

    class MetricsSection(Vertical):
        """Always-on bottom block with a section label and three metric cards."""

        def __init__(self) -> None:
            super().__init__(id="metrics", classes="metrics-section")
            self.border_title = "METRICS"

        def compose(self) -> ComposeResult:
            with Horizontal(id="metric-cards"):
                yield ActivityCard()
                yield ProgressCard()
                yield StatusCard()

        def refresh_snapshot(self, snapshot: MetricsSnapshot) -> None:
            """Push one snapshot into the title and the cards.

            Each card owns its body; the section never computes metrics.
            """
            self._paint_title(snapshot.plan_title)
            self.query_one("#metric-heatmap", ActivityCard).refresh_activity(snapshot.activity)
            self.query_one("#metric-progress", ProgressCard).refresh_progress(
                snapshot.progress,
                scoped=snapshot.plan_id is not None,
            )
            self.query_one("#metric-status", StatusCard).refresh_status(snapshot.status)

        def _paint_title(self, plan_title: str) -> None:
            """Name the scoped plan, or keep the plain label for all plans."""
            title = "METRICS"
            if plan_title:
                safe = truncate(escape_markup(plan_title), SCOPE_TITLE_WIDTH)
                title = f"METRICS · {safe}"
            self.border_title = title
