"""Startup health check: run it off the UI thread, then open the modal."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from ...setup.health import HealthFinding, HealthReport
from ...setup.integrations import ReviewResult
from ...shared.help import hint_bar
from ..launch import Restart
from ..screens import TextScreen
from ..screens.health import INSTALL, LATER, NEVER, HealthScreen

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
        self.app.run_worker(self._worker, thread=True, group="health")

    def _worker(self) -> None:
        assert self.check is not None
        try:
            session = self.check()
            report = session.report()
        except Exception:  # noqa: BLE001 - a failed check must never break the TUI
            return
        self.app.call_from_thread(self.apply, session, report)

    def apply(self, session: HealthSession, report: HealthReport) -> None:
        """Store the report, update the chip, and prompt for open errors."""
        self.session = session
        self.report = report
        self.refresh_hints()
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
        installed = tuple(item for finding in fixable for item in finding.items)
        missed = {item.id for item in result.pending}
        done = tuple(item for item in installed if item.id not in missed)
        self.app.exit(Restart(tuple(self.report.hosts(done))))

    def chip(self) -> str:
        """Status-line text naming how many findings exist, hidden ones included."""
        count = len(self.report.findings) if self.report is not None else 0
        if not count:
            return ""
        return f" · [reverse] health [/]{count} {'issue' if count == 1 else 'issues'}"

    def refresh_hints(self) -> None:
        """Repaint the key hints with the health chip on the end."""
        from textual.widgets import Label

        chip = self.chip()
        width = max(10, self.app.size.width - 2 - len(chip))
        self.app.query_one("#hints", Label).update(hint_bar(width, markup=True) + chip)
