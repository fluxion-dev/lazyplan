"""The agents pane: one row per live claim, hidden when nobody holds a task."""

from __future__ import annotations

import time
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ....core.ports.coordination import CoordinationPort
from ..query import query_one_opt
from ..views.agents import claim_line, claims_summary, rank_claims


class AgentsPanel(VerticalScroll):
    """Who is working on which task, from claims alone."""

    can_focus = False

    def __init__(self) -> None:
        super().__init__(id="agents")
        self.border_title = " agents "
        self.display = False
        self._claims: list[dict[str, Any]] = []
        self._painted_width = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="agents-body")

    def _row_width(self) -> int | None:
        """Content cells available to one row, or None before the first layout.

        The panel's inner width is current as soon as its Resize lands, while
        the body Static may still report the previous width mid-refresh. Prefer
        the panel and subtract the body's one-cell side padding.
        """
        panel = self.content_size.width
        if panel > 2:
            return panel - 2
        body = query_one_opt(self, "#agents-body", Static)
        width = (body.size.width if body is not None else self.size.width) or self.size.width - 2
        return width if width > 0 else None

    def on_resize(self, event: events.Resize) -> None:
        """Re-wrap claim rows after the terminal width changes."""
        self.call_after_refresh(self._rewrap)

    def _rewrap(self) -> None:
        """Repaint only when the row width actually changed."""
        width = self._row_width()
        if width is None or width == self._painted_width:
            return
        self._paint_rows()

    def show(self, store: CoordinationPort) -> None:
        """Repaint from the store's live claims."""
        claims = store.list_claims()
        self._claims = rank_claims(claims)
        self.display = bool(claims)
        self.border_subtitle = claims_summary(claims) if claims else ""
        self._paint_rows()
        self.scroll_home(animate=False)

    def _paint_rows(self) -> None:
        body = query_one_opt(self, "#agents-body", Static)
        if body is None:
            return
        width = self._row_width()
        self._painted_width = width or 0
        stamp = time.time()
        emoji = getattr(getattr(self.app, "state", None), "emoji", True)
        body.update(
            "\n".join(claim_line(claim, stamp, width, emoji=emoji) for claim in self._claims)
        )
