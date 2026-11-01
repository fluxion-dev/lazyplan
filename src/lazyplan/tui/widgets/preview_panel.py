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
        self.query_one("#preview-body", Static).update(document.render())

    def show_text(self, text: str) -> None:
        self.query_one("#preview-body", Static).update(text)
