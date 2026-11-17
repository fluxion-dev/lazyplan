"""The notification log overlay: timestamped rows, newest at the bottom."""

from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import OptionList, Static
    from textual.widgets.option_list import Option

    from ..controllers.notifications import NotificationEntry, NotificationLog
    from ..navigation import NAV_BINDINGS
    from ..widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from ...shared.design import action_bar

EMPTY_LOG = "Nothing logged yet — messages appear here instead of toasts."

if _TEXTUAL_OK:

    class NotificationLogScreen(Screen):
        """Every captured notification for this session, newest last."""

        navigation_name = "log"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("x", "clear", "Clear"),
            Binding("y", "copy", "Copy"),
        ]

        def __init__(self, log: NotificationLog) -> None:
            super().__init__()
            self._log = log

        @property
        def entries(self) -> tuple[NotificationEntry, ...]:
            """The rows this screen shows, oldest first."""
            return self._log.snapshot()

        def compose(self) -> ComposeResult:
            with Vertical(id="log-page"):
                yield Static("", id="log-head")
                with VerticalScroll(id="log-scroll"):
                    yield OptionList(id="log-list")
                yield Taskbar("", id="log-hints")

        def on_mount(self) -> None:
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#log-page").border_title = " notification log "
            self.query_one("#log-scroll").border_title = " entries "
            # Opening the log reads every warning and error.
            self._log.mark_read()
            self._render_entries()
            self.query_one("#log-list", OptionList).focus()
            self.query_one("#log-hints", Taskbar).set_for_app(
                action_bar(
                    None,
                    [("↑↓", "scroll"), ("x", "clear"), ("y", "copy"), ("esc", "close")],
                ),
            )
            self.app.refresh_taskbar()  # type: ignore[attr-defined]

        def refresh_entries(self) -> None:
            """Repaint after a message arrives while the log is open."""
            if not self.is_mounted:
                return
            self._render_entries()

        def _head(self, count: int) -> str:
            noun = "notification" if count == 1 else "notifications"
            return f"{count} {noun} · session only · newest last · x clear · y copy · esc close"

        def _render_entries(self) -> None:
            entries = self._log.snapshot()
            self.query_one("#log-head", Static).update(self._head(len(entries)))
            listing = self.query_one("#log-list", OptionList)
            highlighted = listing.highlighted
            listing.clear_options()
            if not entries:
                listing.add_option(Option(EMPTY_LOG, disabled=True))
                return
            for index, entry in enumerate(entries):
                listing.add_option(Option(entry.text(), id=str(index)))
            if highlighted is None or highlighted >= len(entries):
                highlighted = len(entries) - 1
            listing.highlighted = highlighted
            listing.scroll_to_highlight()

        def _selected(self) -> NotificationEntry | None:
            entries = self._log.snapshot()
            index = self.query_one("#log-list", OptionList).highlighted
            if index is None or not 0 <= index < len(entries):
                return None
            return entries[index]

        def action_clear(self) -> None:
            """Drop every entry and the unread chip."""
            self._log.clear()
            self._render_entries()
            self.app.refresh_taskbar()  # type: ignore[attr-defined]

        def action_copy(self) -> None:
            """Copy the selected entry as one plain line."""
            entry = self._selected()
            if entry is None:
                return
            self.app.copy_to_clipboard(entry.text())  # type: ignore[attr-defined]
            self.notify(f"copied {entry.clock}")

        def action_back(self) -> None:
            """Close the overlay and return to the screen below."""
            self.app.pop_screen()
