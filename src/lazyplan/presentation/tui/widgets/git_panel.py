"""The GIT pane: a compact checkout and provenance card."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..query import query_one_opt
from ..views.git import GitDocument


class GitPanel(VerticalScroll):
    """Scroll container with one body Static and a live border subtitle."""

    def __init__(self) -> None:
        super().__init__(id="git")
        self.border_title = " git "
        self.display = False
        self._document: GitDocument | None = None
        self._error = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="git-body")

    def on_resize(self, event: events.Resize) -> None:
        """Repaint at the new height and keep the scroll position reachable."""
        self.call_after_refresh(self._reflow)

    def _reflow(self) -> None:
        if self._document is not None:
            self._paint(self._document, home=False)
        elif self._error:
            self._paint_error(self._error)
        self._clamp_scroll()

    def _clamp_scroll(self) -> None:
        """A shorter card may leave the old offset past the content."""
        target = min(self.scroll_y, self.max_scroll_y)
        if target != self.scroll_y:
            self.scroll_to(y=target, animate=False)

    def show(self, document: GitDocument) -> None:
        if query_one_opt(self, "#git-body", Static) is None:
            return
        if not document.body:
            self.show_empty("", "")
            return
        self._document = document
        self._error = ""
        self.display = True
        self._paint(document, home=True)

    def show_empty(self, _title: str, _hint: str) -> None:
        """Hide the pane; a checkout card with no checkout is noise."""
        self.display = False
        self.border_subtitle = ""
        self._document = None
        self._error = ""
        self.scroll_home(animate=False)

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        if query_one_opt(self, "#git-body", Static) is None:
            return
        self._document = None
        self._error = text
        self.display = True
        self._paint_error(text)

    def _paint(self, document: GitDocument, *, home: bool) -> None:
        body = query_one_opt(self, "#git-body", Static)
        if body is None:
            return
        body.remove_class("git-error")
        body.update(document.render())
        self.border_subtitle = document.summary
        if home:
            self.scroll_home(animate=False)
        else:
            self._clamp_scroll()

    def _paint_error(self, text: str) -> None:
        body = query_one_opt(self, "#git-body", Static)
        if body is None:
            return
        body.add_class("git-error")
        body.update(f"[red]{text}[/]")
        self.border_subtitle = ""
        self._clamp_scroll()
