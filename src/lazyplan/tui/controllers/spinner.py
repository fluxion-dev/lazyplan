"""The doing-row spinner: frame timing, row labels, and paint."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from ...design import SPINNER_FRAMES, SPINNER_INTERVAL, apply_mark, status_prefix
from ...models import Status
from ..views.rows import row_text

if TYPE_CHECKING:
    from ..app import LazyplanApp


class SpinnerController:
    """Own the spinner timer and the doing-row label cache."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.tick = 0
        self.rows: dict[tuple[str, int], str] = {}
        self.enabled = True
        self.timer: Any = None

    def start(self) -> None:
        """Start the frame timer unless LAZYPLAN_NO_SPINNER is set."""
        self.enabled = not os.environ.get("LAZYPLAN_NO_SPINNER", "").strip()
        if self.enabled:
            self.timer = self.app.set_interval(SPINNER_INTERVAL, self.spin)

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def remember(self, key: tuple[str, int], status: Status, label: str) -> None:
        """Keep the label after the status prefix for doing rows only."""
        if status != Status.DOING:
            return
        prefix = status_prefix(Status.DOING)
        if label.startswith(prefix):
            self.rows[key] = label[len(prefix) :]

    def spin(self) -> None:
        """Advance one frame; idle when nothing is doing."""
        if not self.enabled or not self.rows:
            return
        self.tick = (self.tick + 1) % len(SPINNER_FRAMES)
        self.paint()

    def paint(self) -> None:
        """Repaint doing rows at the current frame, without rebuilding."""
        prefix = status_prefix(Status.DOING, self.tick)
        for key, suffix in self.rows.items():
            node = self.app._row_nodes.get(key)
            if node is not None:
                node.set_label(row_text(prefix + apply_mark(suffix, key in self.app.marked)))
