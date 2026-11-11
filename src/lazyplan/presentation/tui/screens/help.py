"""TUI screens: modal forms and overlays.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from textual import events, on  # noqa: F401
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

from ...shared.design import HELP_TEXT
from ...shared.palette import Command, matching

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

    class TextScreen(HelpScreen):
        """Read-only text overlay with a custom title and body."""

        def __init__(self, title: str, text: str) -> None:
            super().__init__()
            self.dialog_title = title
            self.HELP = text  # type: ignore[misc]

    class ReleaseNotesScreen(TextScreen):
        """Read-only, scrollable release notes overlay."""

        def __init__(self, text: str) -> None:
            super().__init__("RELEASE NOTES", text)

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
                mode = cmds[0].mode.upper() if cmds else ""
                opts.append(Option(f"── {mode} · {header} ──", disabled=True))
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
                return "Commands — type, ↑/↓ move, enter runs, esc cancels"
            count = sum(len(cmds) for _, cmds in sections)
            noun = "command" if count == 1 else "commands"
            return f"Commands — {count} {noun} · ↑/↓ move"

        @staticmethod
        def _highlight_first(lst: OptionList) -> None:
            """Skip disabled section headers so Enter runs a real command."""
            for index in range(lst.option_count):
                if not lst.get_option_at_index(index).disabled:
                    lst.highlighted = index
                    return

        @staticmethod
        def _next_enabled(disabled: list[bool], current: int | None, delta: int) -> int | None:
            """Next enabled option index, wrapping around the list."""
            count = len(disabled)
            if not count:
                return None
            start = current if current is not None else (-1 if delta > 0 else 0)
            step = 1 if delta > 0 else -1
            for offset in range(1, count + 1):
                candidate = (start + step * offset) % count
                if not disabled[candidate]:
                    return candidate
            return None

        def _move_highlight(self, delta: int) -> None:
            try:
                lst = self.query_one("#palette-list", OptionList)
            except Exception:
                return
            disabled = [lst.get_option_at_index(i).disabled for i in range(lst.option_count)]
            target = self._next_enabled(disabled, lst.highlighted, delta)
            if target is not None:
                lst.highlighted = target

        def on_key(self, event: events.Key) -> None:
            """Keep the search field focused while arrows move the highlight."""
            if event.key in ("up", "down"):
                self._move_highlight(-1 if event.key == "up" else 1)
                event.stop()
            elif event.key in ("pageup", "pagedown"):
                self._move_highlight(-5 if event.key == "pageup" else 5)
                event.stop()

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
                self._highlight_first(self.query_one("#palette-list", OptionList))
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
            self._highlight_first(lst)
            e.stop()

        @on(Input.Submitted, "#palette-input")
        def _run_first(self, e: Input.Submitted) -> None:
            try:
                lst = self.query_one("#palette-list", OptionList)
                index = lst.highlighted
                if index is not None:
                    option = lst.get_option_at_index(index)
                    if not option.disabled and option.id:
                        self.dismiss(str(option.id))
                        return
            except Exception:
                pass
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
