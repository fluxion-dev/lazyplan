"""Startup health check: run it off the UI thread, then open the modal."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...setup.health import HealthReport
from ..screens.health import HealthScreen

if TYPE_CHECKING:
    from ..app import LazyplanApp

HealthCheck = Callable[[], HealthReport]


class HealthController:
    """Own the startup report and the health modal."""

    def __init__(self, app: LazyplanApp, check: HealthCheck | None = None) -> None:
        self.app = app
        self.check = check
        self.report: HealthReport | None = None

    def start(self) -> None:
        """Run the check once in a worker; no check means it is switched off."""
        if self.check is None:
            return
        self.app.run_worker(self._worker, thread=True, group="health")

    def _worker(self) -> None:
        assert self.check is not None
        try:
            report = self.check()
        except Exception:  # noqa: BLE001 - a failed check must never break the TUI
            return
        self.app.call_from_thread(self.apply, report)

    def apply(self, report: HealthReport) -> None:
        """Store the report and open the modal when an open error needs attention."""
        self.report = report
        if report.should_prompt:
            self.app.push_screen(HealthScreen(report))
