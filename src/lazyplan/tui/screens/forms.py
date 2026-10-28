"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

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

    class NewPlanScreen(_Form):
        """Create-plan form: title + why + what, all labeled."""

        def __init__(self, defaults: dict[str, str] | None = None) -> None:
            super().__init__()
            self._defaults = defaults or {}

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("New plan")
                yield Label("Title")
                yield Input(
                    value=self._defaults.get("title", ""), placeholder="title", id="f-title"
                )
                yield Label("Why")
                yield TextArea(
                    self._defaults.get("why", ""),
                    placeholder="why does this exist?",
                    id="f-why",
                )
                yield Label("What")
                yield TextArea(
                    self._defaults.get("what", ""),
                    placeholder="what gets built?",
                    id="f-what",
                )
                with _row():
                    yield Button("Create", id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    "title": self.query_one("#f-title", Input).value.strip(),
                    "why": self.query_one("#f-why", TextArea).text.strip(),
                    "what": self.query_one("#f-what", TextArea).text.strip(),
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.action_cancel()

    class NewMilestoneScreen(_Form):
        """Create-milestone form for one plan."""

        def __init__(
            self,
            plan_id: int,
            defaults: dict[str, str] | None = None,
            context: str = "",
        ) -> None:
            super().__init__()
            self.plan_id = plan_id
            self._defaults = defaults or {}
            self._where = context or f"P{plan_id}"

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New milestone in {self._where}")
                yield Label("Title")
                yield Input(
                    value=self._defaults.get("title", ""), placeholder="title", id="f-title"
                )
                yield Label("Details")
                yield TextArea(
                    self._defaults.get("desc", ""),
                    placeholder="what user value does this slice deliver?",
                    id="f-desc",
                )
                with _row():
                    yield Button("Create", id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    "title": self.query_one("#f-title", Input).value.strip(),
                    "desc": self.query_one("#f-desc", TextArea).text.strip(),
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.action_cancel()

    class NewTaskScreen(_Form):
        """Create-task form for one milestone."""

        def __init__(
            self,
            milestone_id: int,
            defaults: dict[str, str] | None = None,
            context: str = "",
        ) -> None:
            super().__init__()
            self.milestone_id = milestone_id
            self._defaults = defaults or {}
            self._where = context or f"M{milestone_id}"

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New task in {self._where}")
                yield Label("Title")
                yield Input(
                    value=self._defaults.get("title", ""), placeholder="title", id="f-title"
                )
                yield Label("Details")
                yield TextArea(
                    self._defaults.get("desc", ""),
                    placeholder="approach, inputs, prerequisites",
                    id="f-desc",
                )
                with _row():
                    yield Button("Create", id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    "title": self.query_one("#f-title", Input).value.strip(),
                    "desc": self.query_one("#f-desc", TextArea).text.strip(),
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.action_cancel()

    class ConfirmScreen(_Form):
        """One destructive confirmation; dismisses True on the confirm button."""

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
