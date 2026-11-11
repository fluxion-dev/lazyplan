"""TUI screens: modal forms and overlays.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

try:
    from textual import on  # noqa: F401
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.screen import ModalScreen, Screen  # noqa: F401
    from textual.widgets import (  # noqa: F401
        Button,
        Checkbox,
        Input,
        Label,
        OptionList,
        Static,
        TextArea,
    )
    from textual.widgets.option_list import Option  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False


if TYPE_CHECKING:
    pass
from .base import _Form, _row

if _TEXTUAL_OK:

    @dataclass(frozen=True)
    class FormField:
        """One labeled create-form field."""

        key: str
        label: str
        placeholder: str
        field_id: str
        multiline: bool = False

    class EntityForm(_Form):
        """One labeled create form driven by a field spec."""

        dialog_title = "CREATE"
        heading = ""
        fields: tuple[FormField, ...] = ()
        submit_label = "Create"

        def __init__(
            self,
            defaults: dict[str, str] | None = None,
            context: str = "",
            editing: bool = False,
        ) -> None:
            super().__init__()
            self._defaults = defaults or {}
            self._where = context
            self._editing = editing
            self.dialog_title = "EDIT" if editing else "CREATE"

        def _title(self) -> str:
            label = self.heading.replace("New ", "Edit ", 1) if self._editing else self.heading
            return f"{label} in {self._where}" if self._where else label

        def compose(self) -> ComposeResult:
            classes = ["entity-form"]
            if any(field.multiline for field in self.fields):
                classes.append("form-tall")
            with self._dialog(*classes):
                yield Label(self._title(), classes="form-title")
                for field in self.fields:
                    yield Label(field.label, classes="field-label")
                    value = self._defaults.get(field.key, "")
                    if field.multiline:
                        yield TextArea(value, placeholder=field.placeholder, id=field.field_id)
                    else:
                        yield Input(value=value, placeholder=field.placeholder, id=field.field_id)
                with _row():
                    label = "Save" if self._editing else self.submit_label
                    yield Button(label, id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        def _values(self) -> dict[str, str]:
            values: dict[str, str] = {}
            for field in self.fields:
                if field.multiline:
                    values[field.key] = self.query_one(f"#{field.field_id}", TextArea).text.strip()
                else:
                    values[field.key] = self.query_one(f"#{field.field_id}", Input).value.strip()
            return values

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(self._values())

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.action_cancel()

    class NewPlanScreen(EntityForm):
        """Create-plan form: title, why, and what."""

        heading = "New plan"
        fields = (
            FormField("title", "Title", "title", "f-title"),
            FormField("why", "Why", "why does this exist?", "f-why", multiline=True),
            FormField("what", "What", "what gets built?", "f-what", multiline=True),
        )

    class NewMilestoneScreen(EntityForm):
        """Create-milestone form for one plan."""

        heading = "New milestone"
        fields = (
            FormField("title", "Title", "title", "f-title"),
            FormField(
                "desc",
                "Details",
                "what user value does this slice deliver?",
                "f-desc",
                multiline=True,
            ),
        )

        def __init__(
            self,
            plan_id: int,
            defaults: dict[str, str] | None = None,
            context: str = "",
            editing: bool = False,
        ) -> None:
            super().__init__(defaults, context or f"P{plan_id}", editing=editing)
            self.plan_id = plan_id

    class NewTaskScreen(EntityForm):
        """Create-task form for one milestone."""

        heading = "New task"
        fields = (
            FormField("title", "Title", "title", "f-title"),
            FormField(
                "desc", "Details", "approach, inputs, prerequisites", "f-desc", multiline=True
            ),
        )

        def __init__(
            self,
            milestone_id: int,
            defaults: dict[str, str] | None = None,
            context: str = "",
            editing: bool = False,
        ) -> None:
            super().__init__(defaults, context or f"M{milestone_id}", editing=editing)
            self.milestone_id = milestone_id

    class RefScreen(EntityForm):
        """Link one external reference to a plan."""

        heading = "Link external reference"
        submit_label = "Link"
        fields = (
            FormField("url", "URL", "https://…", "r-url"),
            FormField("kind", "Type", "issue, epic, doc, other", "r-kind"),
            FormField("title", "Title", "short label (optional)", "r-title"),
        )

    class ConfirmScreen(_Form):
        """One destructive confirmation; dismisses True on the confirm button."""

        dialog_title = "CONFIRM"

        def __init__(
            self,
            text: str,
            confirm_label: str = "Delete",
            variant: Literal["default", "primary", "success", "warning", "error"] = "error",
        ) -> None:
            super().__init__()
            self.text = text
            self.confirm_label = confirm_label
            self.variant = variant

        def compose(self) -> ComposeResult:
            with self._dialog():
                yield Static(self.text, markup=False)
                with _row():
                    yield Button(self.confirm_label, id="ok", variant=self.variant)
                    yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            """Default to the safe choice: Enter cancels, it does not delete."""
            try:
                self.query_one("#cancel", Button).focus()
            except Exception:
                pass

        @on(Button.Pressed, "#ok")
        def _confirm(self) -> None:
            self.dismiss(True)

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(False)

    class FilterPromptScreen(_Form):
        """Prompt for one line of text; empty clears the filter."""

        dialog_title = "FILTER"

        def __init__(
            self,
            title: str = "Filter tree by text (empty clears)",
            placeholder: str = "filter text…",
            submit_label: str = "Apply",
            initial: str = "",
        ) -> None:
            super().__init__()
            self._title = title
            self._placeholder = placeholder
            self._submit_label = submit_label
            self._initial_text = initial
            self.dialog_title = self._infer_title(title)

        @staticmethod
        def _infer_title(title: str) -> str:
            """Name the prompt after the thing it changes, not its widget type."""
            lower = title.lower()
            if "criterion" in lower:
                return "CRITERION"
            if "approve" in lower:
                return "APPROVE"
            if "session" in lower:
                return "SESSION"
            if "comment" in lower:
                return "COMMENT"
            if "note" in lower:
                return "NOTE"
            if "pull request" in lower:
                return "PULL REQUEST"
            if "reference" in lower:
                return "REFERENCE"
            if "delete" in lower:
                return "DELETE"
            return "FILTER"

        def compose(self) -> ComposeResult:
            with self._dialog():
                yield Label(self._title)
                yield Input(
                    value=self._initial_text,
                    placeholder=self._placeholder,
                    id="filter-input",
                )
                with _row():
                    yield Button(self._submit_label, id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            try:
                self.query_one("#filter-input", Input).focus()
            except Exception:
                pass

        @on(Button.Pressed, "#ok")
        def _apply(self) -> None:
            self.dismiss(self.query_one("#filter-input", Input).value.strip())

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

        @on(Input.Submitted, "#filter-input")
        def _submit(self) -> None:
            self.dismiss(self.query_one("#filter-input", Input).value.strip())

    class CriterionScreen(_Form):
        """Add or edit one criterion's text and completion."""

        dialog_title = "CRITERION"

        def __init__(self, text: str = "", done: bool = False, creating: bool = False) -> None:
            super().__init__()
            self._text = text
            self._done = done
            self._creating = creating

        def compose(self) -> ComposeResult:
            heading = "Add criterion" if self._creating else "Edit criterion"
            action = "Add" if self._creating else "Save"
            with self._dialog("entity-form"):
                yield Label(heading, classes="form-title")
                yield Label("Text", classes="field-label")
                yield Input(value=self._text, placeholder="what must be true?", id="c-text")
                yield Checkbox("Done", value=self._done, id="c-done")
                with _row():
                    yield Button(action, id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            super().on_mount()
            self.query_one("#c-text", Input).focus()

        def _values(self) -> dict[str, object]:
            return {
                "text": self.query_one("#c-text", Input).value.strip(),
                "done": self.query_one("#c-done", Checkbox).value,
            }

        @on(Button.Pressed, "#ok")
        def _save(self) -> None:
            self.dismiss(self._values())

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.action_cancel()

        @on(Input.Submitted, "#c-text")
        def _submit(self) -> None:
            self.dismiss(self._values())
