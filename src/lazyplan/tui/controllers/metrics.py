"""Debounced metrics refresh for the selected plan's dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ... import metrics as metrics_mod
from ..metrics import MetricsSection
from ..query import query_one_opt

if TYPE_CHECKING:
    from ..app import LazyplanApp

DEBOUNCE_SECONDS = 0.12


class MetricsController:
    """Own the debounce timer and push scoped snapshots into the dashboard."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.timer: Any = None

    def request(self) -> None:
        """Refresh after the cursor settles, replacing a pending refresh."""
        self.stop()
        self.timer = self.app.set_timer(DEBOUNCE_SECONDS, self.refresh)

    def refresh(self) -> None:
        """Push one snapshot for the current selection into the section."""
        self.stop()
        section = query_one_opt(self.app, "#metrics", MetricsSection)
        if section is None:
            return
        snapshot = metrics_mod.snapshot(self.app.store, plan_id=self.app._plan_ctx())
        section.refresh_snapshot(snapshot)

    def stop(self) -> None:
        """Cancel a pending refresh."""
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
