"""The GIT pane: a compact checkout and provenance card."""

from __future__ import annotations

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

    def compose(self) -> ComposeResult:
        yield Static("", id="git-body")

    def show(self, document: GitDocument) -> None:
        body = query_one_opt(self, "#git-body", Static)
        if body is None:
            return
        if not document.body:
            self.show_empty("", "")
            return
        self.display = True
        body.remove_class("git-error")
        body.update(document.render())
        self.border_subtitle = document.summary
        self.scroll_home(animate=False)

    def show_empty(self, _title: str, _hint: str) -> None:
        """Hide the pane; a checkout card with no checkout is noise."""
        self.display = False
        self.border_subtitle = ""
        self.scroll_home(animate=False)

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        body = query_one_opt(self, "#git-body", Static)
        if body is None:
            return
        self.display = True
        body.add_class("git-error")
        body.update(f"[red]{text}[/]")
        self.border_subtitle = ""
        self.scroll_home(animate=False)
