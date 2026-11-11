"""The preview panel: a sticky title over a scrollable Markdown document body."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Markdown, Static

from ...shared.design import empty_state
from ..views.preview import PreviewDocument


class PreviewPanel(Vertical):
    """Sticky header plus a scrollable Markdown body fed by a PreviewDocument."""

    def __init__(self) -> None:
        super().__init__(id="preview")
        self.border_title = " overview "
        self.border_subtitle = " e edit · c commands "

    def compose(self) -> ComposeResult:
        yield Static("", id="preview-head")
        yield Static("", id="preview-strip")
        with VerticalScroll(id="preview-scroll"):
            yield Markdown("", id="preview-body", open_links=False)
        yield Static("", id="preview-empty", classes="pane-empty")

    def show(self, document: PreviewDocument, strip: str = "") -> None:
        head = self.query_one("#preview-head", Static)
        strip_widget = self.query_one("#preview-strip", Static)
        body = self.query_one("#preview-body", Markdown)
        self._show_content()
        head.remove_class("preview-error")
        body.remove_class("preview-error")
        head.update(document.render_head())
        body.update(document.render_markdown())
        strip_widget.display = bool(strip)
        strip_widget.update(strip)
        self.border_subtitle = " e edit · c commands "
        self._home()

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
        head = self.query_one("#preview-head", Static)
        body = self.query_one("#preview-body", Markdown)
        strip = self.query_one("#preview-strip", Static)
        self._show_content()
        head.update("")
        strip.display = False
        body.add_class("preview-error")
        body.update(f"**preview unavailable**\n\n{text}")
        self.border_subtitle = ""
        self._home()

    @on(Markdown.LinkClicked, "#preview-body")
    def _open_link(self, event: Markdown.LinkClicked) -> None:
        """Open http/https links; other schemes explain instead of launching."""
        if event.href.lower().startswith(("http://", "https://")):
            self.app.open_url(event.href)
            self.app.notify(f"opened {event.href}", timeout=4)
        else:
            self.app.notify(f"cannot open {event.href}; only http and https links open", timeout=4)
        event.stop()
