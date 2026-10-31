"""Shared card base for the metrics dashboard."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

if _TEXTUAL_OK:

    class MetricCard(Vertical):
        """One titled metrics card with an explicit empty state."""

        def __init__(self, card_id: str, title: str, empty: str) -> None:
            super().__init__(id=card_id, classes="metric-card")
            self.card_title = title
            self._empty = empty

        def compose(self) -> ComposeResult:
            yield Label(self.card_title, classes="metric-title")
            yield Static(self._empty, id=f"{self.id}-body", classes="metric-body")

        def show(self, markup: str) -> None:
            """Replace the card body with *markup*."""
            self.query_one(f"#{self.id}-body", Static).update(markup)

        def show_empty(self) -> None:
            """Restore the card's empty state."""
            self.show(self._empty)
