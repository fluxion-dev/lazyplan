"""The bottom metrics section and its card slots."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.containers import Horizontal, Vertical

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...metrics import MetricsSnapshot
from ..query import query_one_opt
from .timeline import TimelineCard

__all__ = ["MetricsSection"]

if _TEXTUAL_OK:

    class MetricsSection(Vertical):
        """Always-on bottom block with the timeline card."""

        def __init__(self) -> None:
            super().__init__(id="metrics", classes="metrics-section")

        def compose(self) -> ComposeResult:
            with Horizontal(id="metric-cards"):
                yield TimelineCard()

        def refresh_snapshot(self, snapshot: MetricsSnapshot) -> None:
            """Push one snapshot into the card; the section never computes metrics."""
            card = query_one_opt(self, "#metric-timeline", TimelineCard)
            if card is not None:
                card.refresh_timeline(snapshot.timeline)
