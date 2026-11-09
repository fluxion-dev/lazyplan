"""Finish an agent work session with a summary and handoff."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Input, Label, TextArea

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class AgentFinishScreen(ModalScreen[tuple[str, str] | None]):
        """Collect the handoff before closing a work session."""

        BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

        def compose(self) -> ComposeResult:
            with Vertical(id="agent-finish"):
                yield Label("Finish this work session", classes="form-title")
                yield Label("Summary", classes="field-label")
                yield TextArea("", id="finish-summary")
                yield Label("Handoff", classes="field-label")
                yield Input(placeholder="next: ...", id="finish-handoff")
                with Horizontal(classes="btn-row"):
                    yield Button("Finish", id="finish-apply", variant="primary")
                    yield Button("Cancel", id="finish-cancel")

        def on_mount(self) -> None:
            self.query_one("#agent-finish").border_title = "FINISH"

        def _close(self) -> None:
            summary = self.query_one("#finish-summary", TextArea).text.strip()
            handoff = self.query_one("#finish-handoff", Input).value.strip()
            self.dismiss((summary, handoff))

        def action_cancel(self) -> None:
            self.dismiss(None)

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "finish-apply":
                self._close()
            elif event.button.id == "finish-cancel":
                self.dismiss(None)
