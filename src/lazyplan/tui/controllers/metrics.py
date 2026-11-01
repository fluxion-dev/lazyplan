"""Debounced metrics refresh for the selected plan's dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ... import metrics as metrics_mod
from ..metrics import MetricsSection
from ..query import query_one_opt

if TYPE_CHECKING:
    from ..app import LazyplanApp

DEBOUNCE_SECONDS = 0.12
NOW_TICK_SECONDS = 15.0


class MetricsController:
    """Own the debounce timer and push scoped snapshots into the dashboard."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.timer: Any = None
        self.now_timer: Any = None

    def start(self) -> None:
        """Start the periodic now tick that advances open lanes."""
        if self.now_timer is None:
            self.now_timer = self.app.set_interval(NOW_TICK_SECONDS, self.refresh_now)

    def request(self) -> None:
        """Refresh after the cursor settles, replacing a pending refresh."""
        self._stop_debounce()
        self.timer = self.app.set_timer(DEBOUNCE_SECONDS, self.refresh)

    def refresh(self) -> None:
        """Push one snapshot for the current selection into the section."""
        self._stop_debounce()
        section = query_one_opt(self.app, "#metrics", MetricsSection)
        if section is None:
            return
        selected = self.app.selected
        snapshot = metrics_mod.snapshot(
            self.app.store,
            plan_id=self.app._plan_ctx(),
            scope_kind=selected[0] if selected is not None else None,
            scope_id=selected[1] if selected is not None else None,
        )
        section.refresh_snapshot(snapshot)

    def refresh_now(self) -> None:
        """Advance open lanes silently while no modal screen is open."""
        if self.now_timer is None or not self.app._mounted:
            return
        if len(self.app.screen_stack) <= 1:
            self.refresh()

    def stop(self) -> None:
        """Cancel the debounce and now timers."""
        self._stop_debounce()
        if self.now_timer is not None:
            self.now_timer.stop()
            self.now_timer = None

    def _stop_debounce(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
