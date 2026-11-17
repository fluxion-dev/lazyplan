"""Modal-palette Textual TUI: nav tree + live preview, one status line.

Keys: j/k navigate, left/right fold, c palette, escape clear.
  Press c then type a prefix (new, cycle, criteria, fold, filter, ...) and enter runs it.
  Mouse click selects; the overview follows the selection.
Keyboard-only: agents use the `lpui` CLI against the same SQLite file; local edits
bump reactive rev, external DB changes arrive via a structural fingerprint() poll
plus a live_fingerprint() poll that the feed toast summarizes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from textual import events
    from textual.app import ComposeResult, SeverityLevel
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.message import Message
    from textual.reactive import reactive
    from textual.widgets import Static, Tree
    from textual.widgets.tree import TreeNode

    from ..shared.tree_nav import NavTree  # noqa: F401
    from .navigation import NAV_BINDINGS
    from .query import query_one_opt
    from .widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...infrastructure import settings
from ...store import Store
from ..cli.parser import package_version
from ..shared.design import (
    EMPTY_PLAN_QUEUE_HINT,
    EMPTY_PLAN_QUEUE_TITLE,
    PANEL_PLAN_QUEUE_TITLE,
    PANEL_PLAN_REVIEW_TITLE,
    empty_state,
)
from .actions import ActionMixin
from .base import AppBase
from .controllers.git_state import GitStateController
from .controllers.health import HealthCheck, HealthController
from .controllers.metrics import MetricsController
from .controllers.notifications import NotificationLog
from .controllers.setup import SetupController, WizardCheck
from .controllers.tree import TreeController
from .controllers.updates import UpdateController
from .filters import FilterMixin
from .launch import Restart, launch_notes, launch_update, relaunch, take_restart_notice
from .metrics import MetricsSection
from .preview import PreviewMixin
from .screens import ReleaseNotesScreen
from .state import AppState
from .theme import register_themes, remembered_theme
from .tree import TreeMixin
from .widgets.agents_panel import AgentsPanel
from .widgets.git_panel import GitPanel
from .widgets.plan_tree import FoldTree
from .widgets.preview_panel import PreviewPanel

CSS_DIR = Path(__file__).parent / "css"


if _TEXTUAL_OK:

    class NotificationsChanged(Message):
        """A notification joined the log; every visible bar may need a repaint."""

    class LazyplanApp(
        TreeMixin,
        PreviewMixin,
        FilterMixin,
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
            *NAV_BINDINGS,
            Binding("escape", "clear_filter", "Back", show=False),
            Binding("t", "cycle_theme", "Theme"),
            Binding("T", "toggle_timeline", "Timeline"),
            Binding("S", "open_setup", "Setup"),
            Binding("n", "new_context", "New"),
            Binding("e", "edit_selection", "Edit"),
            Binding("s", "toggle_status", "Status"),
            Binding("a", "add_criterion", "Criterion"),
            Binding("d", "delete", "Delete"),
            Binding("g", "source_trail", "Source"),
            Binding("z", "fold", "Fold", show=False),
            Binding("Z", "fold_all", "Fold all", show=False),
            Binding("slash", "filter_text", "Filter"),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("m", "open_maintenance", "Maintain"),
            Binding("U", "update_prompt", "Update"),
            Binding("W", "release_notes", "Notes"),
        ]
        rev = reactive(0, init=False)

        def watch_rev(self, _old: int, _new: int) -> None:
            if not self._mounted:
                return
            try:
                self._fp = self.store.fingerprint()
                self._live_fp = self.store.live_fingerprint()
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
            changed = self._narrow is not narrow
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
                metrics.display = self.state.timeline_shown(narrow)
            screen = self.screen
            screen.set_class(compact, "compact")
            screen.set_class(wide, "wide")
            return changed

        def __init__(self, store: Store) -> None:
            super().__init__()
            register_themes(self, remembered_theme())
            self.store = store
            self.heal = settings.heal_enabled(settings.heal_mode())
            self.state = AppState()
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._row_labels: dict[tuple[str, int], str] = {}
            self._row_specs = {}
            self.tree_controller = TreeController(self)
            self.update_controller = UpdateController(self)
            self.health_controller = HealthController(self)
            self.setup_controller = SetupController(self)
            self.git_state_controller = GitStateController(self)
            self.metrics_controller = MetricsController(self)
            self._fp: Any = store.fingerprint()
            self._live_fp: Any = store.live_fingerprint()
            self._last_event_id: int = 0
            events = store.feed(1)
            if events:
                self._last_event_id = int(events[0]["id"])
            self._startup_notice: str = ""
            self._startup_notes: str = ""
            self.notification_log = NotificationLog()

        def notify(
            self,
            message: str,
            *,
            title: str = "",
            severity: SeverityLevel = "information",
            timeout: float | None = None,
            markup: bool = True,
            source: str = "",
        ) -> None:
            """Log every message; ordinary notices never raise a toast."""
            self.notification_log.append(
                message,
                severity=severity,
                source=source or self._notification_source(),
            )
            self.post_message(NotificationsChanged())

        def notify_toast(
            self,
            message: str,
            *,
            title: str = "",
            severity: SeverityLevel = "information",
            timeout: float | None = None,
            markup: bool = True,
            source: str = "",
        ) -> None:
            """Log the message and toast it; startup and update notices only."""
            self.notify(message, severity=severity, source=source)
            super().notify(
                message,
                title=title,
                severity=severity,
                timeout=timeout,
                markup=markup,
            )

        def _notification_source(self) -> str:
            """The active screen's name, so every entry says where it came from."""
            try:
                screen = self.screen
            except Exception:  # noqa: BLE001 - a closing screen may race a worker
                return "tree"
            named = str(getattr(screen, "navigation_name", "") or "")
            if named:
                return named
            class_name = type(screen).__name__.removesuffix("Screen")
            return class_name.lower() or "tree"

        def action_update_prompt(self) -> None:
            """Open the update screen for a known or cached newer release."""
            self.update_controller.prompt()

        def action_health_prompt(self) -> None:
            """Open the health check with every finding, hidden ones included."""
            self.health_controller.prompt()

        def refresh_taskbar(self) -> None:
            """Push the current update and log state into every visible taskbar."""
            latest = self.update_controller.latest
            unread = self.notification_log.unread
            for screen in self.screen_stack:
                try:
                    for bar in screen.query(Taskbar):
                        bar.set_latest(latest)
                        bar.set_log_count(unread)
                except Exception:  # noqa: BLE001 - a closing screen may race a poll
                    continue

        def on_notifications_changed(self, _event: NotificationsChanged) -> None:
            """Repaint every bar when a message joins the log."""
            self.refresh_taskbar()

        def action_open_setup(self) -> None:
            """Reopen the setup wizard from the palette or the S key."""
            self.setup_controller.open()

        def action_release_notes(self) -> None:
            """Open the bundled release notes for the installed version."""
            from ...services import notes

            try:
                _releases, text = notes.select_notes(package_version())
            except (OSError, ValueError) as exc:
                self.notify(f"release notes unavailable: {exc}", timeout=10)
                return
            if not text:
                self.notify(f"No release notes for v{package_version()}.", timeout=10)
                return
            self.push_screen(ReleaseNotesScreen(text))

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="left"):
                        with Vertical(id="plans-active", classes="plan-panel"):
                            yield FoldTree("active", id="tree", classes="plan-tree")
                            yield Static(
                                empty_state(EMPTY_PLAN_QUEUE_TITLE, EMPTY_PLAN_QUEUE_HINT),
                                id="tree-empty",
                                classes="pane-empty",
                            )
                        yield AgentsPanel()
                        with Vertical(id="plans-finished", classes="plan-panel"):
                            yield FoldTree("finished", id="tree-finished", classes="plan-tree")
                        yield GitPanel()
                    with Vertical(id="side"):
                        yield PreviewPanel()
                yield MetricsSection()
            yield Taskbar("", id="hints")

        async def _on_resize(self, event: events.Resize) -> None:
            """Textual stops Resize at the App; re-apply the shell after it."""
            await super()._on_resize(event)
            changed = self._apply_layout(event.size.width)
            if self._mounted and changed:
                self.call_after_refresh(self.refresh_all)

        def on_unmount(self) -> None:
            """Stop app-owned timers; each drives deferred or periodic work."""
            self._mounted = False
            self.update_controller.stop()
            self.metrics_controller.stop()

        def check_action(self, action: str, _parameters: tuple[object, ...]) -> bool | None:
            """Keep app-level row actions on the main tree screen.

            A Source, Detail, help, or modal screen owns its own keys; without
            this guard, `d` or `s` pressed there would mutate the hidden main
            selection.
            """
            if len(self.screen_stack) > 1 and action not in ("quit", "help", "update_prompt"):
                return False
            return True

        def on_mount(self) -> None:
            self._mounted = True
            self._apply_layout()
            self.call_after_refresh(lambda: self.refresh_all("ready — ? for help"))
            self.set_interval(0.25, self._poll)
            self.update_controller.start()
            self.metrics_controller.start()
            # The setup check runs first so a pending wizard suppresses the
            # startup health prompt instead of duplicating it.
            self.setup_controller.start(self.health_controller.start)
            self.query_one("#plans-active").border_title = f" {PANEL_PLAN_QUEUE_TITLE} "
            self.query_one("#plans-finished").border_title = f" {PANEL_PLAN_REVIEW_TITLE} "
            if self._startup_notice:
                self.notify_toast(self._startup_notice, timeout=10, source="startup")
            if self._startup_notes:
                notes = self._startup_notes
                self.call_after_refresh(lambda: self.push_screen(ReleaseNotesScreen(notes)))
            tree = self.query_one("#tree", Tree)
            if tree.display:
                tree.focus()

    def create_app(
        db_path: str | None = None,
        startup_notice: str = "",
        startup_notes: str = "",
        health_check: HealthCheck | None = None,
        restart_notice: str = "",
        wizard_check: WizardCheck | None = None,
    ) -> LazyplanApp:
        """Build the app bound to a store."""
        app = LazyplanApp(Store(db_path))
        app._startup_notice = startup_notice
        app._startup_notes = startup_notes
        app.health_controller.check = health_check
        app.health_controller.restart_notice = restart_notice
        app.setup_controller.check = wizard_check
        return app


def _startup_checks(
    db_path: str | None,
) -> tuple[HealthCheck | None, WizardCheck | None]:
    """The two read-only startup checks, built once from one cwd and version."""
    from ..setup.triggers import setup_off

    if setup_off(db_path):
        return None, None
    from ..setup.health import current as health_check
    from .controllers.setup import current as wizard_check

    cwd, version = Path.cwd(), package_version()
    return (
        lambda: health_check(cwd, version=version),
        wizard_check(cwd, version=version),
    )


def run(db_path: str | None = None) -> int:
    """Run the TUI; exit 3 when Textual is missing."""
    if not _TEXTUAL_OK:
        print("Textual not installed. Run: pip install -e . then: lpui ui")
        print("Fallback (no TUI): lpui list")
        return 3
    startup_notice, exit_now = launch_update()
    if exit_now:
        return 0
    health_check, wizard_check = _startup_checks(db_path)
    app = create_app(
        db_path,
        startup_notice,
        launch_notes(),
        health_check=health_check,
        restart_notice=take_restart_notice(),
        wizard_check=wizard_check,
    )
    result = app.run()
    if isinstance(result, Restart):
        return relaunch(result)
    return 0
