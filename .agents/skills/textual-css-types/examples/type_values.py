"""CSS type example for the Textual skill suite."""

from textual.app import App, ComposeResult
from textual.widgets import Static


class TypeValues(App):
    """Use a border, colour, scalar, text style, and percentage."""

    CSS = """
    #card {
        border: solid $primary;
        color: $text;
        width: 80%;
        min-height: 3;
        padding: 1 2;
        text-style: bold;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("valid CSS types", id="card")
