"""TUI screens: modal forms and detail views.

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

        def __init__(self, defaults: dict[str, str] | None = None, context: str = "") -> None:
            super().__init__()
            self._defaults = defaults or {}
            self._where = context

        def _title(self) -> str:
            return f"{self.heading} in {self._where}" if self._where else self.heading

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(self._title(), classes="form-title")
                for field in self.fields:
                    yield Label(field.label, classes="field-label")
                    value = self._defaults.get(field.key, "")
                    if field.multiline:
                        yield TextArea(value, placeholder=field.placeholder, id=field.field_id)
                    else:
                        yield Input(value=value, placeholder=field.placeholder, id=field.field_id)
                with _row():
                    yield Button(self.submit_label, id="ok", variant="primary")
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
        ) -> None:
            super().__init__(defaults, context or f"P{plan_id}")
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
        ) -> None:
            super().__init__(defaults, context or f"M{milestone_id}")
            self.milestone_id = milestone_id

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
            with Vertical(id="dlg"):
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

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
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
