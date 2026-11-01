"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    )
    from textual.widgets.option_list import Option  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...design import HELP_TEXT
from ...palette import Command, matching

if TYPE_CHECKING:
    pass
from .base import _Form, _row

if _TEXTUAL_OK:

    class HelpScreen(_Form):
        """Shared help text overlay; same source as `lpui help`."""

        HELP = HELP_TEXT
        dialog_title = "HELP"

        def on_mount(self) -> None:
            super().on_mount()
            help_panel = self.query_one("#help")
            help_panel.border_title = self.dialog_title

        def compose(self) -> ComposeResult:
            with Vertical(id="help"):
                with VerticalScroll(id="help-scroll"):
                    yield Static(self.HELP, markup=False)
                with _row():
                    yield Button("Close", id="cancel")

        @on(Button.Pressed, "#cancel")
        def _close(self) -> None:
            self.dismiss(None)

    class PaletteScreen(_Form):
        """Modal command palette: grouped sections, live filter, context rules."""

        dialog_title = "COMMANDS"

        def __init__(self, context: dict[str, str | None] | None = None) -> None:
            super().__init__()
            self._ctx = context or {}

        @staticmethod
        def _matching(query: str) -> list[tuple[str, list[Command]]]:
            """Non-empty sections for a query; headers never match."""
            return matching(query)

        def _section_options(self, sections: list[tuple[str, list[Command]]]) -> list[Option]:
            opts: list[Option] = []
            for header, cmds in sections:
                opts.append(Option(f"── {header} ──", disabled=True))
                for cmd in cmds:
                    reason = self._ctx.get(cmd.id)
                    label = f"{cmd.label}  ({cmd.key})" if cmd.key else cmd.label
                    if reason:
                        label += f" — {reason}"
                    opts.append(Option(label, id=cmd.id, disabled=bool(reason)))
            if not opts:
                opts.append(Option("No matching commands", disabled=True))
            return opts

        def _title(self, sections: list[tuple[str, list[Command]]], query: str) -> str:
            if not query.strip():
                return "Commands — type to search, enter to run, esc cancels"
            count = sum(len(cmds) for _, cmds in sections)
            noun = "command" if count == 1 else "commands"
            return f"Commands — {count} {noun}"

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(
                    self._title(self._matching(""), ""),
                    id="palette-title",
                )
                yield Input(placeholder="search commands…", id="palette-input")
                with VerticalScroll(id="palette-scroll"):
                    yield OptionList(*self._section_options(self._matching("")), id="palette-list")

        def on_mount(self) -> None:
            try:
                self.query_one("#palette-input", Input).focus()
            except Exception:
                pass

        @on(Input.Changed, "#palette-input")
        def _filter(self, e: Input.Changed) -> None:
            try:
                lst = self.query_one("#palette-list", OptionList)
                title = self.query_one("#palette-title", Label)
            except Exception:
                return
            sections = self._matching(e.value)
            lst.clear_options()
            for opt in self._section_options(sections):
                lst.add_option(opt)
            title.update(self._title(sections, e.value))
            e.stop()

        @on(Input.Submitted, "#palette-input")
        def _run_first(self, e: Input.Submitted) -> None:
            for _, cmds in self._matching(e.value):
                for cmd in cmds:
                    if not self._ctx.get(cmd.id):
                        self.dismiss(cmd.id)
                        return
            self.dismiss(None)

        @on(OptionList.OptionSelected, "#palette-list")
        def _pick(self, e: OptionList.OptionSelected) -> None:
            opt_id = getattr(getattr(e, "option", None), "id", None)
            if opt_id:
                self.dismiss(str(opt_id))
            e.stop()
