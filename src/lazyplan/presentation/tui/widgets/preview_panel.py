"""The preview panel: a sticky title over a scrollable document body."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ...shared.design import empty_state
from ..views.preview import PreviewDocument


class PreviewPanel(Vertical):
    """Sticky header plus a scrollable body fed by a PreviewDocument."""

    def __init__(self) -> None:
        super().__init__(id="preview")
        self.border_title = " overview "
        self.border_subtitle = " e edit · c commands "
        self._document: PreviewDocument | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="preview-head")
        yield Static("", id="preview-strip")
        with VerticalScroll(id="preview-scroll"):
            yield Static("", id="preview-body")
        yield Static("", id="preview-empty", classes="pane-empty")

    def show(self, document: PreviewDocument, strip: str = "") -> None:
        head = self.query_one("#preview-head", Static)
        strip_widget = self.query_one("#preview-strip", Static)
        self._show_content()
        self._document = document
        head.remove_class("preview-error")
        self.query_one("#preview-body", Static).remove_class("preview-error")
        head.update(document.render_head())
        self._render_body()
        strip_widget.display = bool(strip)
        strip_widget.update(strip)
        self.border_subtitle = " e edit · c commands "
        self._home()

    def _render_body(self) -> None:
        """Render the body at the current width so section bars span it."""
        if self._document is None:
            return
        body = self.query_one("#preview-body", Static)
        width = body.size.width
        body.update(self._document.render_body(width if width > 0 else None))

    def on_resize(self) -> None:
        """Keep section bars as wide as the pane after a resize."""
        self._render_body()

    def _home(self) -> None:
        try:
            self.query_one("#preview-scroll", VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass

    def _show_content(self) -> None:
        """Show the normal head and scroll body, hiding the empty state."""
        self.query_one("#preview-head", Static).display = True
        self.query_one("#preview-scroll", VerticalScroll).display = True
        self.query_one("#preview-empty", Static).display = False

    def show_empty(self, title: str, hint: str) -> None:
        """A centered empty state with a clear next action."""
        self._document = None
        self.query_one("#preview-head", Static).display = False
        self.query_one("#preview-strip", Static).display = False
        self.query_one("#preview-scroll", VerticalScroll).display = False
        empty = self.query_one("#preview-empty", Static)
        empty.display = True
        empty.update(empty_state(title, hint))
        self.border_subtitle = ""
        self._home()

    def show_error(self, text: str) -> None:
        """A visible load failure instead of a blank pane."""
        self._document = None
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Static)
        strip = self.query_one("#preview-strip", Static)
        self._show_content()
        head.update("")
        strip.display = False
        body.add_class("preview-error")
        body.update(f"[bold red]preview unavailable[/]\n\n[dim]{text}[/]")
        self.border_subtitle = ""
        self._home()
