"""Shared card base for the metrics dashboard."""

from __future__ import annotations

try:
    from textual.containers import Vertical

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

if _TEXTUAL_OK:

    class MetricCard(Vertical):
        """One titled metrics card with an explicit empty state."""

        def __init__(self, card_id: str, title: str, empty: str) -> None:
            super().__init__(id=card_id, classes="metric-card")
            self.card_title = title
            self.empty = empty
