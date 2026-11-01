"""Update polling, the shared gate, the chip, and the once-per-version toast."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...cli.parser import package_version
from ...upgrade import (
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
from ..screens.update import UpdateScreen

if TYPE_CHECKING:
    from ..app import LazyplanApp


class UpdateController:
    """Own the update timer and the status-chip state."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.notice: str | None = None
        self.latest: str = ""
        self.info: Any = None
        self.toasted_version: str = ""
        self.timer: Any = None
        self.checking: bool = False

    def start(self) -> None:
        """Start the cache poll and run one check immediately."""
        self.timer = self.app.set_interval(poll_interval(), self.tick)
        self.tick()

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def tick(self) -> None:
        """Poll the shared cache; one update worker runs at a time."""
        if not self.app._mounted or self.checking:
            return
        if not update_check_enabled():
            return
        self.checking = True
        self.app.run_worker(self._refresh_worker, thread=True, group="update")

    def _refresh_worker(self) -> None:
        """Read the cache and refresh the network when the gate allows."""
        try:
            latest = refresh_update()
        except Exception:
            latest = None
        try:
            self.app.call_from_thread(self.apply_update, latest)
        except Exception:
            pass

    def apply_update(self, latest: str | None) -> None:
        """Show or clear the chip after one update poll."""
        self.checking = False
        if latest is None:
            return
        info = detect()
        notice = notice_text(info, package_version(), latest)
        if notice is None:
            self.clear()
            return
        self.announce(notice, latest, info)

    def clear(self) -> None:
        """Drop the chip once the installed version catches up."""
        if self.notice is None and not self.latest:
            return
        self.notice = None
        self.latest = ""
        self.info = None
        self.app._refresh_status()

    def announce(self, notice: str, latest: str = "", info: Any = None) -> None:
        """Store the chip and toast once per version."""
        self.notice = notice
        self.latest = latest
        self.info = info
        if latest and latest != self.toasted_version:
            self.toasted_version = latest
            self.app.notify(notice, timeout=8)
        self.app._refresh_status()

    def prompt(self) -> None:
        """Open the update screen for a known or cached newer release."""
        latest = self.latest or (cached_latest(max_age=UPDATE_CACHE_TTL) or "")
        if not latest:
            self.app.notify("no update available")
            return
        installed = package_version()
        try:
            if parse_version(latest) <= parse_version(installed):
                self.app.notify(f"lpui v{installed} is up to date")
                return
        except UpgradeError:
            self.app.notify("cannot compare the update versions")
            return
        info = self.info or detect()
        self.app.push_screen(UpdateScreen(installed, latest, info))
