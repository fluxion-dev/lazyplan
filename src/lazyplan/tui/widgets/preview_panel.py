"""The preview panel: a scrollable card fed by a PreviewDocument."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..views.preview import PreviewDocument


class PreviewPanel(VerticalScroll):
    """Scroll container with a single body Static."""

    def __init__(self) -> None:
        super().__init__(id="preview")
        self.border_title = "PREVIEW"

    def compose(self) -> ComposeResult:
        yield Static("", id="preview-body")

    def show(self, document: PreviewDocument) -> None:
        body = self.query_one("#preview-body", Static)
        body.remove_class("preview-empty", "preview-error")
        body.update(document.render())

    def show_empty(self, title: str, hint: str) -> None:
        """A two-line empty state with a clear next action."""
        body = self.query_one("#preview-body", Static)
        body.remove_class("preview-error")
        body.add_class("preview-empty")
        body.update(f"[bold]{title}[/]\n\n[dim]{hint}[/]")

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        body = self.query_one("#preview-body", Static)
        body.remove_class("preview-empty")
        body.add_class("preview-error")
        body.update(f"[bold red]preview unavailable[/]\n\n[dim]{text}[/]")
