"""Startup health check: run it off the UI thread, then open the modal."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from ...setup.health import HealthFinding, HealthReport
from ...setup.integrations import ReviewResult
from ..launch import Restart
from ..screens.health import INSTALL, HealthScreen

if TYPE_CHECKING:
    from ..app import LazyplanApp


class HealthSession(Protocol):
    """What the controller needs from one startup check."""

    def report(self) -> HealthReport: ...

    def install(self, findings: tuple[HealthFinding, ...]) -> ReviewResult: ...


HealthCheck = Callable[[], HealthSession]


class HealthController:
    """Own the startup report and the health modal."""

    def __init__(self, app: LazyplanApp, check: HealthCheck | None = None) -> None:
        self.app = app
        self.check = check
        self.session: HealthSession | None = None
        self.report: HealthReport | None = None

    def start(self) -> None:
        """Run the check once in a worker; no check means it is switched off."""
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
        """Store the report and open the modal when an open error needs attention."""
        self.session = session
        self.report = report
        if report.should_prompt:
            self.app.push_screen(HealthScreen(report), self.on_choice)

    def on_choice(self, action: str | None) -> None:
        """Install and restart, or leave everything as it is."""
        if action != INSTALL or self.session is None or self.report is None:
            return
        fixable = tuple(finding for finding in self.report.open if finding.fixable)
        try:
            result = self.session.install(fixable)
        except OSError as exc:
            self.app.notify(f"install failed: {exc}", severity="error", timeout=15)
            return
        installed = tuple(item for finding in fixable for item in finding.items)
        missed = {item.id for item in result.pending}
        done = tuple(item for item in installed if item.id not in missed)
        self.app.exit(Restart(tuple(self.report.hosts(done))))
