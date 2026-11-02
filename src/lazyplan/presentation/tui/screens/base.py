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
        TextArea,
    )
    from textual.widgets.option_list import Option  # noqa: F401

    from ..query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False


if TYPE_CHECKING:
    pass

if _TEXTUAL_OK:

    def _row(*buttons: Button) -> Horizontal:
        """One compact action row (`.btn-row`): every modal row."""
        return Horizontal(*buttons, classes="btn-row")

    class _Form(ModalScreen):
        """Modal form base: Esc cancels, dirty drafts confirm first."""

        BINDINGS = [Binding("escape", "cancel", "Cancel")]
        dialog_title = "ACTION"

        def __init__(self) -> None:
            super().__init__()
            self._initial: tuple[str, ...] | None = None

        def on_mount(self) -> None:
            """Snapshot the starting values so Esc can tell a draft from a no-op."""
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            dialog = query_one_opt(self, "#dlg")
            if dialog is not None:
                dialog.border_title = self.dialog_title
            self._initial = self._snapshot()

        def _snapshot(self) -> tuple[str, ...]:
            values: list[str] = []
            for widget in self.query(Input):
                values.append(widget.value)
            for area in self.query(TextArea):
                values.append(area.text)
            return tuple(values)

        def action_cancel(self) -> None:
            """Close cleanly, or ask before throwing away a draft."""
            if self._initial is not None and self._snapshot() != self._initial:
                from .forms import ConfirmScreen

                def cb(confirmed: bool | None) -> None:
                    if confirmed:
                        self.dismiss(None)

                self.app.push_screen(
                    ConfirmScreen(
                        "Discard this draft?",
                        confirm_label="Discard",
                        variant="warning",
                    ),
                    cb,
                )
                return
            self.dismiss(None)
