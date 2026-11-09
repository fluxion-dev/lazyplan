"""The GIT pane: a compact checkout and provenance card."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ...shared.design import empty_state
from ..views.git import GitDocument


class GitPanel(VerticalScroll):
    """Scroll container with one body Static and a live border subtitle."""

    def __init__(self) -> None:
        super().__init__(id="git")
        self.border_title = " git "

    def compose(self) -> ComposeResult:
        yield Static("", id="git-body")
        yield Static("", id="git-empty", classes="pane-empty")

    def _show_body(self) -> None:
        """Show the normal body and hide the empty state."""
        self.query_one("#git-body", Static).display = True
        self.query_one("#git-empty", Static).display = False

    def show(self, document: GitDocument) -> None:
        body = self.query_one("#git-body", Static)
        self._show_body()
        body.remove_class("git-error")
        body.update(document.render())
        self.border_subtitle = document.summary
        self.scroll_home(animate=False)

    def show_empty(self, title: str, hint: str) -> None:
        """A centered empty state with a clear next action."""
        self.query_one("#git-body", Static).display = False
        empty = self.query_one("#git-empty", Static)
        empty.display = True
        empty.update(empty_state(title, hint))
        self.border_subtitle = ""
        self.scroll_home(animate=False)

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        body = self.query_one("#git-body", Static)
        self._show_body()
        body.add_class("git-error")
        body.update(f"[red]{text}[/]")
        self.border_subtitle = ""
        self.scroll_home(animate=False)
