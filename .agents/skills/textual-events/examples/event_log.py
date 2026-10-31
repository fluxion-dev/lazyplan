"""Key and custom-message example for the Textual skill suite."""

from textual import events
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Static


class Saved(Message):
    """A custom message with a stable handler name."""


class EventLog(App):
    """Show the on_key and on_saved handlers."""

    def compose(self) -> ComposeResult:
        yield Static("press a key", id="log")

    def on_key(self, event: events.Key) -> None:
        """Record the key, then post a custom message."""
        self.query_one("#log", Static).update(f"key: {event.key}")
        if event.key == "s":
            self.post_message(Saved())

    def on_saved(self) -> None:
        """React to the custom message."""
        self.query_one("#log", Static).update("saved")
