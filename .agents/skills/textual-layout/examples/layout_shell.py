"""Container and screen layout example for the Textual skill suite."""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Label, Static


class LayoutShell(App):
    """A header, two panes, a scrolling list, and a footer."""

    CSS = """
    #main { height: 1fr; }
    #nav { width: 1fr; border-right: solid $primary; }
    #preview { width: 2fr; }
    #list { height: 1fr; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="nav"):
                yield Label("Navigation")
                yield Static("Plans")
            with VerticalScroll(id="preview"):
                yield Label("Preview")
                for index in range(20):
                    yield Static(f"Row {index}", id=f"row-{index}")
        yield Footer()
