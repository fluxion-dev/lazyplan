"""Guide example: actions, screen composition, and a headless test target."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static


class GuidedApp(App):
    """Small app used to show the guide's app/testing workflow."""

    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("guide example", id="body")
        yield Footer()

    def action_focus_body(self) -> None:
        """Example action used by the guide's action table."""
        self.query_one("#body", Static).update("action ran")
