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
    from textual import events
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.reactive import reactive
    from textual.widgets import Label, Tree
    from textual.widgets.tree import TreeNode

    from ..tree_nav import NavTree  # noqa: F401
    from .query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..cli.parser import package_version
from ..store import Store
from ..update_stage import apply_on_launch, clear_failure, read_failure
from .actions import ActionMixin
from .base import AppBase
from .bulk import BulkMixin
from .controllers.git_state import GitStateController
from .controllers.spinner import SpinnerController
from .controllers.tree import TreeController
from .controllers.updates import UpdateController
from .filters import FilterMixin
from .metrics import MetricsSection
from .preview import PreviewMixin
from .state import AppState
from .theme import register_themes
from .tree import TreeMixin
from .widgets.plan_tree import FoldTree
from .widgets.preview_panel import PreviewPanel

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
            """Apply the compact, narrow, and wide shell tiers."""
            main = query_one_opt(self, "#main", Horizontal)
            if main is None:
                return False
            available = self.size.width if width is None else width
            narrow = available < 100
            compact = available < 80
            wide = available >= 120
            changed = (
                self._narrow is not narrow
                or self.state.compact is not compact
                or self.state.wide is not wide
            )
            self._narrow = narrow
            self.state.compact = compact
            self.state.wide = wide
            main.set_class(narrow, "narrow")
            main.set_class(compact, "compact")
            main.set_class(wide, "wide")
            panel = query_one_opt(self, "#panel", Vertical)
            if panel is not None:
                panel.set_class(compact, "compact")
            metrics = query_one_opt(self, "#metrics", MetricsSection)
            if metrics is not None:
                metrics.set_class(narrow, "narrow")
            screen = self.screen
            screen.set_class(compact, "compact")
            screen.set_class(wide, "wide")
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
            self.spinner_controller = SpinnerController(self)
            self.git_state_controller = GitStateController(self)
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()
            self._startup_notice: str = ""

        def action_update_prompt(self) -> None:
            """Open the update screen for a known or cached newer release."""
            self.update_controller.prompt()

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="nav"):
                        yield FoldTree("plans", id="tree")
                    yield PreviewPanel()
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
            self.spinner_controller.stop()

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
            self.spinner_controller.start()
            self.update_controller.start()
            if self._startup_notice:
                self.notify(self._startup_notice, timeout=10)
            self.query_one("#tree", Tree).focus()

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
