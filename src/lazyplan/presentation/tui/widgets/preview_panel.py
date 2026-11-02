"""The preview panel: a sticky title over a scrollable document body."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ..views.preview import PreviewDocument


class PreviewPanel(Vertical):
    """Sticky header plus a scrollable body fed by a PreviewDocument."""

    def __init__(self) -> None:
        super().__init__(id="preview")
        self.border_title = " preview "
        self.border_subtitle = " enter open · e edit "

    def compose(self) -> ComposeResult:
        yield Static("", id="preview-head")
        with VerticalScroll(id="preview-scroll"):
            yield Static("", id="preview-body")

    def show(self, document: PreviewDocument) -> None:
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Static)
        body.remove_class("preview-empty", "preview-error")
        head.remove_class("preview-empty", "preview-error")
        head.update(document.render_head())
        body.update(document.render_body())
        self.border_subtitle = " enter open · e edit "
        self._home()

    def _home(self) -> None:
        try:
            self.query_one("#preview-scroll", VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass

    def show_empty(self, title: str, hint: str) -> None:
        """A two-line empty state with a clear next action."""
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Static)
        head.update("")
        body.remove_class("preview-error")
        body.add_class("preview-empty")
        body.update(f"[bold]{title}[/]\n\n[dim]{hint}[/]")
        self.border_subtitle = ""
        self._home()

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Static)
        head.update("")
        body.remove_class("preview-empty")
        body.add_class("preview-error")
        body.update(f"[bold red]preview unavailable[/]\n\n[dim]{text}[/]")
        self.border_subtitle = ""
        self._home()
