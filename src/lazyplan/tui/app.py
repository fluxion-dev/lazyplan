"""Modal-palette Textual TUI: nav tree + live preview, one status line.

Keys: j/k navigate, left/right fold, enter detail, c palette,
  escape clear. Press c then type a prefix (new, cycle, tick,
  fold, filter, ...) and enter runs the match.
  Mouse click selects; double-click opens detail.
Keyboard-only: agents use the `lpui` CLI against the same SQLite file; local edits
bump reactive rev, external DB changes arrive via fingerprint() poll + feed toast.
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    from textual import events, on  # noqa: F401
    from textual.app import App, ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.reactive import reactive  # noqa: F401
    from textual.widgets import Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ..tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..cli.parser import package_version
from ..design import (
    APP_CSS,
    SPINNER_FRAMES,
    SPINNER_INTERVAL,
    status_prefix,
)
from ..models import Status
from ..store import Store
from ..update_stage import apply_on_launch, clear_failure, read_failure
from ..upgrade import (
    UPDATE_CACHE_TTL,
    UpgradeError,
    cached_latest,
    detect,
    notice_text,
    parse_version,
    poll_interval,
    refresh_update,
    update_check_enabled,
)
from .actions import ActionMixin
from .base import AppBase
from .bulk import BulkMixin
from .filters import FilterMixin
from .preview import PreviewMixin
from .screens.update import UpdateScreen
from .tree import FoldTree, TreeMixin

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row


if _TEXTUAL_OK:

    class LazyplanApp(
        TreeMixin,
        PreviewMixin,
        FilterMixin,
        BulkMixin,
        ActionMixin,
        AppBase,
    ):
        """Single-panel TUI: the plan tree."""

        TITLE = "lazyplan"
        CSS = APP_CSS
        ENABLE_COMMAND_PALETTE = False
        BINDINGS = [
            Binding("enter", "open_detail", "Open"),
            Binding("space", "toggle_mark", "Mark"),
            Binding("escape", "clear_filter", "Back", show=False),
            Binding("c", "command_palette", "Palette"),
            Binding("n", "new_context", "New"),
            Binding("e", "edit_selection", "Edit"),
            Binding("s", "toggle_status", "Status"),
            Binding("x", "criteria", "Tick"),
            Binding("a", "add_criterion", "Criterion"),
            Binding("d", "delete", "Delete"),
            Binding("g", "source_trail", "Source"),
            Binding("z", "fold", "Fold", show=False),
            Binding("Z", "fold_all", "Fold all", show=False),
            Binding("slash", "filter_text", "Filter"),
            Binding("f", "filter_status", "Status filter", show=False),
            Binding("F", "filter_source", "Source filter", show=False),
            Binding("A", "toggle_show_all", "All plans", show=False),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("U", "update_prompt", "Update"),
            Binding("question_mark", "help", "Help"),
            Binding("q", "quit", "Quit"),
        ]
        rev = reactive(0, init=False)

        def watch_rev(self, _old: int, _new: int) -> None:
            if not self._mounted:
                return
            try:
                self._fp = self.store.fingerprint()
            except Exception:
                pass
            note = self._pending_note
            self._pending_note = ""
            try:
                self.refresh_all(note)
            except Exception:
                pass

        def _apply_layout(self, width: int | None = None) -> bool:
            """Two panes when there is room; one pane on narrow terminals."""
            try:
                main = self.query_one("#main", Horizontal)
            except Exception:
                return False
            available = self.size.width if width is None else width
            narrow = available < 100
            changed = self._narrow is not narrow
            self._narrow = narrow
            main.set_class(narrow, "narrow")
            return changed

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self.selected: tuple[str, int] | None = None
            self.status_filter: Status | None = None
            self.show_all: bool = False
            self.filter_text: str = ""
            self.source_filter: str = "all"
            self.marked: set[tuple[str, int]] = set()
            self._undo: list[dict] | None = None
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._row_labels: dict[tuple[str, int], str] = {}
            self._collapsed: set[tuple[str, int]] = set()
            self._expanded: set[tuple[str, int]] = set()
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()
            self._update_notice: str | None = None
            self._update_latest: str = ""
            self._update_info: Any = None
            self._startup_notice: str = ""
            self._update_toasted: bool = False
            self._update_timer: Any = None
            self._update_checking: bool = False
            self._pending_note: str = ""
            self._mounted: bool = False
            self._refreshing: bool = False
            self._preview_key: tuple[str, int] | None = None
            self._dirty_external: bool = False
            self._narrow: bool | None = None
            self._git_cache: dict[str, tuple[float, dict[str, Any]]] = {}
            self._git_pending: set[str] = set()
            self._spinner_tick: int = 0
            self._spinner_rows: dict[tuple[str, int], str] = {}
            self._spinner_enabled: bool = True
            self._spinner_timer: Any = None

        def action_update_prompt(self) -> None:
            """Open the update screen for a known or cached newer release."""
            latest = self._update_latest or (cached_latest(max_age=UPDATE_CACHE_TTL) or "")
            if not latest:
                self.notify("no update available")
                return
            installed = package_version()
            try:
                if parse_version(latest) <= parse_version(installed):
                    self.notify(f"lpui v{installed} is up to date")
                    return
            except UpgradeError:
                self.notify("cannot compare the update versions")
                return
            info = self._update_info or detect()
            self.push_screen(UpdateScreen(installed, latest, info))

        def _update_tick(self) -> None:
            """Poll the shared cache; one update worker runs at a time."""
            if not self._mounted or self._update_checking:
                return
            if not update_check_enabled():
                return
            self._update_checking = True
            self.run_worker(self._refresh_update_worker, thread=True, group="update")

        def _refresh_update_worker(self) -> None:
            """Read the cache and refresh the network when the gate allows."""
            try:
                latest = refresh_update()
            except Exception:
                latest = None
            try:
                self.call_from_thread(self._apply_update, latest)
            except Exception:
                pass

        def _apply_update(self, latest: str | None) -> None:
            """Show the chip after one update poll."""
            self._update_checking = False
            if latest is None:
                return
            info = detect()
            notice = notice_text(info, package_version(), latest)
            if notice is not None:
                self._announce_update(notice, latest, info)

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="nav"):
                        yield FoldTree("plans", id="tree")
                    with VerticalScroll(id="preview"):
                        yield Static("", id="preview-body")
            yield Label("", id="hints")
            yield Label("", id="status")

        async def _on_resize(self, event: events.Resize) -> None:
            """Textual stops Resize at the App; re-apply the shell after it."""
            await super()._on_resize(event)
            changed = self._apply_layout(event.size.width)
            if self._mounted and changed:
                self.call_after_refresh(self.refresh_all)

        def on_unmount(self) -> None:
            """Stop app-owned timers; both drive periodic work."""
            if self._update_timer is not None:
                self._update_timer.stop()
                self._update_timer = None
            if self._spinner_timer is not None:
                self._spinner_timer.stop()
                self._spinner_timer = None

        def check_action(self, action: str, _parameters: tuple[object, ...]) -> bool | None:
            """Keep app-level row actions on the main tree screen.

            A Source, Detail, help, or modal screen owns its own keys; without
            this guard, `d` or `s` pressed there would mutate the hidden main
            selection.
            """
            if len(self.screen_stack) > 1 and action not in ("quit", "help"):
                return False
            return True

        def on_mount(self) -> None:
            self._mounted = True
            self._apply_layout()
            self.refresh_all("ready — ? for help")
            self.set_interval(1.0, self._poll)
            self._spinner_enabled = not os.environ.get("LAZYPLAN_NO_SPINNER", "").strip()
            if self._spinner_enabled:
                self._spinner_timer = self.set_interval(SPINNER_INTERVAL, self._spin)
            self._update_timer = self.set_interval(poll_interval(), self._update_tick)
            self._update_tick()
            if self._startup_notice:
                self.notify(self._startup_notice, timeout=10)
            self.query_one("#tree", Tree).focus()

        def _remember_spinner(
            self,
            key: tuple[str, int],
            status: Status,
            label: str,
        ) -> None:
            """Keep the label after the status prefix for doing rows only."""
            if status != Status.DOING:
                return
            prefix = status_prefix(Status.DOING)
            if label.startswith(prefix):
                self._spinner_rows[key] = label[len(prefix) :]

        def _spin(self) -> None:
            """Advance one frame; idle when nothing is doing."""
            if not self._spinner_enabled or not self._spinner_rows:
                return
            self._spinner_tick = (self._spinner_tick + 1) % len(SPINNER_FRAMES)
            self._paint_spinner()

        def _paint_spinner(self) -> None:
            """Repaint doing rows at the current frame, without rebuilding."""
            prefix = status_prefix(Status.DOING, self._spinner_tick)
            for key, suffix in self._spinner_rows.items():
                node = self._row_nodes.get(key)
                if node is not None:
                    mark = " [bold green]✓[/]" if key in self.marked else ""
                    node.set_label(prefix + suffix + mark)

        def _announce_update(self, notice: str, latest: str = "", info: Any = None) -> None:
            self._update_notice = notice
            self._update_latest = latest
            self._update_info = info
            if not self._update_toasted:
                self._update_toasted = True
                self.notify(notice, timeout=8)
            self._refresh_status()

    def create_app(db_path: str | None = None, startup_notice: str = "") -> LazyplanApp:
        """Build the app bound to a store."""
        app = LazyplanApp(Store(db_path))
        app._startup_notice = startup_notice
        return app


def run(db_path: str | None = None) -> int:
    """Run the TUI; exit 3 when Textual is missing."""
    if not _TEXTUAL_OK:
        print("Textual not installed. Run: pip install -e . then: lpui ui")
        print("Fallback (no TUI): lpui list")
        return 3
    startup_notice = ""
    state, detail = apply_on_launch(package_version())
    if state == "applied":
        try:
            os.execv(sys.executable, [sys.executable, "-m", "lazyplan", *sys.argv[1:]])
        except OSError as exc:
            startup_notice = f"update v{detail} installed — restart lpui ({exc})"
    elif state == "error":
        startup_notice = f"update failed: {detail}"
    elif state == "downgrade":
        startup_notice = f"refused to downgrade to v{detail}"
    else:
        failure = read_failure()
        if failure:
            startup_notice = f"update failed: {failure}"
            clear_failure()
    create_app(db_path, startup_notice).run()
    return 0
