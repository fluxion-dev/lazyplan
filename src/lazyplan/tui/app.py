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
from pathlib import Path
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
    from .query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..cli.parser import package_version
from ..design import (
    SPINNER_FRAMES,
    SPINNER_INTERVAL,
    status_prefix,
)
from ..models import Status
from ..store import Store
from ..update_stage import apply_on_launch, clear_failure, read_failure
from .actions import ActionMixin
from .base import AppBase
from .bulk import BulkMixin
from .controllers.tree import TreeController
from .controllers.updates import UpdateController
from .filters import FilterMixin
from .metrics import MetricsSection
from .preview import PreviewMixin
from .state import AppState
from .theme import register_themes
from .tree import TreeMixin
from .widgets.plan_tree import FoldTree

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row
CSS_DIR = Path(__file__).parent / "css"


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
        CSS_PATH = [
            CSS_DIR / "app.tcss",
            CSS_DIR / "components.tcss",
            CSS_DIR / "screens.tcss",
        ]
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
            main = query_one_opt(self, "#main", Horizontal)
            if main is None:
                return False
            available = self.size.width if width is None else width
            narrow = available < 100
            changed = self._narrow is not narrow
            self._narrow = narrow
            main.set_class(narrow, "narrow")
            metrics = query_one_opt(self, "#metrics", MetricsSection)
            if metrics is not None:
                metrics.set_class(narrow, "narrow")
            return changed

        def __init__(self, store: Store) -> None:
            super().__init__()
            register_themes(self)
            self.store = store
            self.state = AppState()
            self._undo: list[dict] | None = None
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._row_labels: dict[tuple[str, int], str] = {}
            self.tree_controller = TreeController(self)
            self.update_controller = UpdateController(self)
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()
            self._startup_notice: str = ""
            self._git_cache: dict[str, tuple[float, dict[str, Any]]] = {}
            self._git_pending: set[str] = set()
            self._spinner_tick: int = 0
            self._spinner_rows: dict[tuple[str, int], str] = {}
            self._spinner_enabled: bool = True
            self._spinner_timer: Any = None

        def action_update_prompt(self) -> None:
            """Open the update screen for a known or cached newer release."""
            self.update_controller.prompt()

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="nav"):
                        yield FoldTree("plans", id="tree")
                    with VerticalScroll(id="preview"):
                        yield Static("", id="preview-body")
                yield MetricsSection()
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
            self.update_controller.stop()
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
            self.update_controller.start()
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
