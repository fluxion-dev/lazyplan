"""Setup wizard wiring: detect the trigger off the UI thread, then open it.

The check is read-only and takes one boolean: a startup launch asks whether the
trigger is due, while a palette open requests the wizard outright. Both build
the session in the same worker, so a slow or missing host catalog never freezes
the screen.

The screen lives in lane M68's module and is imported lazily; an install
without it keeps a working app and says so instead of failing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...setup.session import SetupSession
from ...setup.triggers import WizardNeed, detect

if TYPE_CHECKING:
    from ..app import LazyplanApp


@dataclass(frozen=True)
class WizardLaunch:
    """One trigger answer, with the session to edit when the wizard is due."""

    need: WizardNeed
    session: SetupSession | None = None

    @property
    def due(self) -> bool:
        """True when this answer opens the wizard."""
        return self.session is not None


WizardCheck = Callable[[bool], WizardLaunch]
ScreenFactory = Callable[[WizardLaunch], Any]


def current(cwd: Path, home: Path | None = None, version: str = "") -> WizardCheck:
    """Read-only trigger and session for the checkout at *cwd*."""

    def check(requested: bool) -> WizardLaunch:
        need = detect(cwd, home, version, requested=requested)
        if not need.due:
            return WizardLaunch(need)
        return WizardLaunch(need, SetupSession.load(cwd, home, version))

    return check


def wizard_screen(launch: WizardLaunch) -> Any:
    """Build the wizard screen for one launch; imported only when it opens."""
    from ..screens import SetupWizardScreen  # type: ignore[attr-defined]  # lane M68

    return SetupWizardScreen(launch.session, launch.need)


class SetupController:
    """Own the startup trigger, the wizard screen, and health suppression."""

    def __init__(self, app: LazyplanApp, check: WizardCheck | None = None) -> None:
        self.app = app
        self.check = check
        self.launch = WizardLaunch(WizardNeed())
        self.screen_factory: ScreenFactory = wizard_screen
        self.opening = False
        self._started = False
        self._then: Callable[[], None] | None = None

    @property
    def pending(self) -> bool:
        """True while a due wizard still owns the launch."""
        return self.launch.due

    def start(self, then: Callable[[], None] | None = None) -> None:
        """Detect the trigger in a worker, then hand over to *then* once."""
        self._then = then
        if not self._started:
            self._started = True
            if self.check is None:
                self._continue()
                return
            self.app.run_worker(lambda: self._worker(False), thread=True, group="setup")
            return
        self._continue()

    def open(self) -> None:
        """Open the wizard on demand from the palette or its key."""
        if self.opening or len(self.app.screen_stack) > 1:
            return
        if self.check is None:
            self.app.notify("setup is unavailable for this database")
            return
        self.opening = True
        self.app.run_worker(lambda: self._worker(True), thread=True, group="setup")

    def on_dismiss(self, result: Any) -> None:
        """Refresh health and the tree after a completed apply."""
        if result is None:
            return
        self.launch = WizardLaunch(WizardNeed())
        self.app.notify("setup applied", timeout=4)
        self.app.health_controller.refresh()
        self.app.refresh_all("setup applied")

    def _worker(self, requested: bool) -> None:
        try:
            assert self.check is not None
            launch = self.check(requested)
        except Exception:  # noqa: BLE001 - a failed check must never break the TUI
            launch = WizardLaunch(WizardNeed())
        self.app.call_from_thread(self._apply, launch)

    def _apply(self, launch: WizardLaunch) -> None:
        self.opening = False
        self.launch = launch
        if not launch.due:
            self._continue()
            return
        self.app.call_after_refresh(self._push)

    def _continue(self) -> None:
        then, self._then = self._then, None
        if then is not None:
            then()

    def _push(self) -> None:
        try:
            self._open_screen()
        finally:
            self._continue()

    def _open_screen(self) -> None:
        if not self.launch.due or len(self.app.screen_stack) > 1:
            return
        try:
            screen = self.screen_factory(self.launch)
        except (ImportError, TypeError) as exc:
            self.app.notify(f"setup wizard unavailable: {exc}", timeout=10)
            return
        self.app.push_screen(screen, self.on_dismiss)
