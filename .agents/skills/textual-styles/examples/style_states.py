"""Style cascade and pseudo-class example for the Textual skill suite."""

from textual.app import App, ComposeResult
from textual.widgets import Static


class StyleStates(App):
    """Show a base class, a state class, and a hover rule."""

    CSS = """
    #box {
        background: $panel;
        color: $text;
        border: round $primary;
        padding: 1 2;
        width: 32;
    }
    #box.active {
        background: $accent;
        color: $text;
        text-style: bold;
    }
    #box:hover {
        border: heavy $accent;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("styled block", id="box")

    def on_mount(self) -> None:
        """Exercise the state class after the widget exists."""
        self.query_one("#box").add_class("active")
