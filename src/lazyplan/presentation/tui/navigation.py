"""Universal navigation host shared by every TUI screen.

Help, palette, quit, and back mean the same thing everywhere. The
main tree keeps its direct keys; source, export, update, and every modal
inherit this host so no screen is a dead end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from textual.binding import Binding

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


@dataclass(frozen=True)
class NavEntry:
    """One visited location in the navigation history."""

    screen: str
    kind: str | None = None
    oid: int | None = None
    label: str = ""

    @property
    def selection(self) -> tuple[str, int] | None:
        """The row this entry restored, when it has one."""
        if self.kind is None or self.oid is None:
            return None
        return (self.kind, self.oid)


@dataclass
class NavigationHistory:
    """Back and forward over visited screens with exact selection restore."""

    entries: list[NavEntry] = field(default_factory=lambda: [NavEntry("tree", label="plans")])
    index: int = 0

    @property
    def current(self) -> NavEntry:
        """The entry the user is looking at."""
        return self.entries[self.index]

    def push(self, entry: NavEntry) -> NavEntry:
        """Append a new location and drop any forward branch."""
        del self.entries[self.index + 1 :]
        self.entries.append(entry)
        self.index = len(self.entries) - 1
        return entry

    def back(self) -> NavEntry | None:
        """Move one step back; None at the oldest entry."""
        if self.index == 0:
            return None
        self.index -= 1
        return self.current

    def forward(self) -> NavEntry | None:
        """Move one step forward; None at the newest entry."""
        if self.index >= len(self.entries) - 1:
            return None
        self.index += 1
        return self.current

    def breadcrumb(self) -> str:
        """Every visited level up to the current one, root first."""
        return " › ".join(entry.label for entry in self.entries[: self.index + 1] if entry.label)


if _TEXTUAL_OK:
    HISTORY_BINDINGS = [
        Binding("[", "history_back", "Back", show=False),
        Binding("]", "history_forward", "Forward", show=False),
    ]
    NAV_BINDINGS = [
        Binding("c", "command_palette", "Palette", priority=True),
        Binding("question_mark", "help", "Help", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        *HISTORY_BINDINGS,
    ]
else:  # pragma: no cover - stdlib-only interpreter
    HISTORY_BINDINGS = []
    NAV_BINDINGS = []


class NavigationMixin:
    """Open the shared overlays from any screen and leave consistently."""

    app: Any

    def check_action(self, action: str, _parameters: tuple[object, ...]) -> bool | None:
        """Let text fields keep printable keys while they are being edited."""
        if action in {"command_palette", "help", "quit"}:
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

    def action_quit(self) -> None:
        """Leave lazyplan from any screen."""
        self.app.exit()

    def action_history_back(self) -> None:
        """Step back through the shared navigation history."""
        handler = getattr(self.app, "action_history_back", None)
        if callable(handler):
            handler()

    def action_history_forward(self) -> None:
        """Step forward through the shared navigation history."""
        handler = getattr(self.app, "action_history_forward", None)
        if callable(handler):
            handler()

    def action_back(self) -> None:
        """Close this screen and return to the previous one."""
        self.app.pop_screen()
