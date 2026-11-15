"""Startup health check: run it off the UI thread, then open the modal."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from ...setup.health import HealthFinding, HealthReport, items_of
from ...setup.integrations import ReviewResult
from ...shared.help import hint_bar
from ..launch import Restart
from ..screens import TextScreen
from ..screens.health import INSTALL, LATER, NEVER, HealthScreen
from ..widgets.taskbar import Taskbar
from .background import run_off_thread

if TYPE_CHECKING:
    from ..app import LazyplanApp

DECISIONS = {LATER: "deferred", NEVER: "never"}


class HealthSession(Protocol):
    """What the controller needs from one startup check."""

    def report(self) -> HealthReport: ...

    def install(self, findings: tuple[HealthFinding, ...]) -> ReviewResult: ...

    def decide(self, findings: tuple[HealthFinding, ...], decision: str) -> None: ...


HealthCheck = Callable[[], HealthSession]


class HealthController:
    """Own the startup report, the health modal, and the status-line chip."""

    def __init__(self, app: LazyplanApp, check: HealthCheck | None = None) -> None:
        self.app = app
        self.check = check
        self.session: HealthSession | None = None
        self.report: HealthReport | None = None
        self.restart_notice = ""
        self.offered: tuple[HealthFinding, ...] = ()

    def start(self) -> None:
        """Show a relaunch's restart notice, then run the check in a worker."""
        if self.restart_notice:
            self.app.push_screen(TextScreen("RESTART YOUR AGENTS", self.restart_notice))
        if self.check is None:
            return
        run_off_thread(self.app, self._check, self._apply, "health")

    def refresh(self) -> None:
        """Re-run the check off the UI thread without offering anything."""
        if self.check is None:
            return
        run_off_thread(
            self.app,
            self._check,
            lambda pair: self.apply(*pair, prompt=False),
            "health",
        )

    def _check(self) -> tuple[HealthSession, HealthReport]:
        assert self.check is not None
        session = self.check()
        return session, session.report()

    def _apply(self, result: tuple[HealthSession, HealthReport]) -> None:
        self.apply(*result)

    def apply(self, session: HealthSession, report: HealthReport, prompt: bool = True) -> None:
        """Store the report, update the chip, and prompt for open errors."""
        self.session = session
        self.report = report
        self.refresh_hints()
        if not prompt:
            return
        if self.app.setup_controller.pending:
            return
        if report.should_prompt:
            self._offer(report.open, review=False)

    def prompt(self) -> None:
        """Open every finding, hidden ones included, from the palette."""
        if self.report is None:
            self.app.notify("health check is not available yet")
            return
        if not self.report.findings:
            self.app.notify("lazyplan has everything it needs")
            return
        self._offer(self.report.findings, review=True)

    def _offer(self, findings: tuple[HealthFinding, ...], review: bool) -> None:
        self.offered = findings
        self.app.push_screen(HealthScreen(findings, review=review), self.on_choice)

    def on_choice(self, action: str | None) -> None:
        """Install and restart, or remember Not now or Never ask."""
        if self.session is None or action is None:
            return
        if action == INSTALL:
            self._install()
            return
        self.session.decide(self.offered, DECISIONS[action])

    def _install(self) -> None:
        assert self.session is not None and self.report is not None
        fixable = tuple(finding for finding in self.offered if finding.fixable)
        try:
            result = self.session.install(fixable)
        except OSError as exc:
            self.app.notify(f"install failed: {exc}", severity="error", timeout=15)
            return
        missed = {item.id for item in result.pending}
        done = tuple(item for item in items_of(fixable) if item.id not in missed)
        self.app.exit(Restart(tuple(self.report.hosts(done))))

    def chip(self) -> str:
        """Status-line text naming how many findings exist, hidden ones included."""
        count = len(self.report.findings) if self.report is not None else 0
        if not count:
            return ""
        return f" · [reverse] health [/]{count} {'issue' if count == 1 else 'issues'}"

    def refresh_hints(self) -> None:
        """Repaint the key hints, health chip, and version badge."""
        width = max(10, self.app.size.width - 4)
        self.app.query_one("#hints", Taskbar).set_for_app(
            hint_bar(width, markup=True),
            health=self.chip(),
        )
