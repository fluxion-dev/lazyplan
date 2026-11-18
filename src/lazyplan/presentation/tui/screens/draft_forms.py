"""Draft annotation form: kind, body, and the selected quote."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.widgets import Button, Label, Select, TextArea

from ....services.draft_content import DraftAnchor
from .base import _Form, _row


class AnnotationForm(_Form):
    """Ask for one comment, question, or change on a draft anchor."""

    dialog_title = "ANNOTATE"

    def __init__(self, anchor: DraftAnchor, label: str) -> None:
        super().__init__()
        self.draft_anchor = anchor
        self.label = label

    def compose(self) -> ComposeResult:
        with self._dialog("entity-form"):
            yield Label(f"Annotate {self.label}", classes="form-title")
            if self.draft_anchor.quote:
                yield Label(f'Quote: "{self.draft_anchor.quote}"', classes="field-label")
            yield Label("Kind", classes="field-label")
            yield Select(
                [("Comment", "comment"), ("Question", "question"), ("Change", "change")],
                value="comment",
                allow_blank=False,
                id="f-kind",
            )
            yield Label("Annotation", classes="field-label")
            yield TextArea(
                "",
                placeholder="What should change, be answered, or be checked?",
                id="f-body",
            )
            with _row():
                yield Button("Save", id="ok", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#f-body", TextArea).focus()

    @on(Button.Pressed, "#ok")
    def _save(self) -> None:
        body = self.query_one("#f-body", TextArea).text.strip()
        if not body:
            self.notify("an annotation needs text", timeout=3)
            return
        kind = str(self.query_one("#f-kind", Select).value)
        self.dismiss({"kind": kind, "body": body})

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.action_cancel()
