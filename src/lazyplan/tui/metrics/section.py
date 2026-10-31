"""The bottom metrics section and its titled card base."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.containers import Vertical
    from textual.widgets import Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...metrics import MetricsSnapshot

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

    class MetricsSection(Vertical):
        """Always-on bottom section that hosts the read-only metric cards."""

        def __init__(self) -> None:
            super().__init__(id="metrics", classes="metrics-section")

        def compose(self) -> ComposeResult:
            yield MetricCard("metric-heatmap", "Activity", "no completions yet")
            yield MetricCard("metric-progress", "Progress", "no plans yet")
            yield MetricCard("metric-status", "Status", "no tasks yet")

        def refresh_snapshot(self, snapshot: MetricsSnapshot) -> None:
            """Push one snapshot into the cards.

            The shell renders empty states; each panel plan replaces its
            card body without changing the host.
            """
