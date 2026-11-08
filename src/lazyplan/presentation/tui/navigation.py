"""Universal navigation host shared by every TUI screen.

Help, palette, quit, override, and back mean the same thing everywhere. The
main tree keeps its direct keys; detail, source, export, update, and every
modal inherit this host so no screen is a dead end.
"""

from __future__ import annotations

from typing import Any

try:
    from textual.binding import Binding

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


if _TEXTUAL_OK:
    NAV_BINDINGS = [
        Binding("c", "command_palette", "Palette", priority=True),
        Binding("question_mark", "help", "Help", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("O", "toggle_override", "Override", priority=True),
    ]
else:  # pragma: no cover - stdlib-only interpreter
    NAV_BINDINGS = []


class NavigationMixin:
    """Open the shared overlays from any screen and leave consistently."""

    app: Any

    def check_action(self, action: str, _parameters: tuple[object, ...]) -> bool | None:
        """Let text fields keep printable keys while they are being edited."""
        if action in {"command_palette", "help", "quit", "toggle_override"}:
            if self._focus_is_text():
                return False
        return True

    def _focus_is_text(self) -> bool:
        """True while an Input or TextArea owns the keyboard."""
        try:
            from textual.widgets import Input, TextArea
        except ImportError:  # pragma: no cover - stdlib-only interpreter
            return False
        focused = self.app.focused
        return isinstance(focused, (Input, TextArea))

    def palette_context(self) -> dict[str, str | None]:
        """Commands disabled for this screen, keyed by palette id."""
        context = getattr(self.app, "_palette_context", None)
        return dict(context()) if callable(context) else {}

    def action_command_palette(self) -> None:
        """Open the palette above this screen."""
        from .screens.help import PaletteScreen

        app: Any = self.app
        palette = PaletteScreen(self.palette_context())
        app.push_screen(palette, app._run_palette_command)

    def action_help(self) -> None:
        """Open the shared help overlay above this screen."""
        from .screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_toggle_override(self) -> None:
        """Toggle manual writes through the app-owned gate."""
        handler = getattr(self.app, "action_toggle_override", None)
        if callable(handler):
            handler()

    def action_quit(self) -> None:
        """Leave lazyplan from any screen."""
        self.app.exit()

    def action_back(self) -> None:
        """Close this screen and return to the previous one."""
        self.app.pop_screen()
