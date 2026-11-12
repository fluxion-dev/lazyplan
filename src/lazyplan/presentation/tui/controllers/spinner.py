"""The doing-row spinner: frame timing, row labels, and paint."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ....core.entities import Status
from ...shared.design import SPINNER_FRAMES, SPINNER_INTERVAL, spinner_enabled, status_prefix
from ..query import query_one_opt
from ..views.rows import row_text
from ..widgets.agents_panel import AgentsPanel

if TYPE_CHECKING:
    from ..app import LazyplanApp


class SpinnerController:
    """Own the spinner timer, the doing-row labels, and the live agents frame."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.tick = 0
        self.rows: dict[tuple[str, int], str] = {}
        self.enabled = True
        self.timer: Any = None

    def start(self) -> None:
        """Start the frame timer unless LAZYPLAN_NO_SPINNER is set."""
        self.enabled = spinner_enabled()
        if self.enabled:
            self.timer = self.app.set_interval(SPINNER_INTERVAL, self.spin)

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None

    def remember(self, key: tuple[str, int], status: Status, label: str) -> None:
        """Keep the label after the status prefix for doing rows only."""
        if status != Status.DOING:
            self.rows.pop(key, None)
            return
        prefix = status_prefix(Status.DOING)
        if label.startswith(prefix):
            self.rows[key] = label[len(prefix) :]

    def spin(self) -> None:
        """Advance one frame; idle when nothing is doing or working."""
        if not self.enabled:
            return
        panel = query_one_opt(self.app, "#agents", AgentsPanel)
        working = panel is not None and panel.has_working()
        if not self.rows and not working:
            return
        self.tick = (self.tick + 1) % len(SPINNER_FRAMES)
        self.paint()
        if working and panel is not None:
            panel.advance(self.tick)

    def paint(self) -> None:
        """Repaint doing rows at the current frame, without rebuilding."""
        frame = self.tick if self.enabled else None
        prefix = status_prefix(Status.DOING, frame)
        for key, suffix in self.rows.items():
            node = self.app._row_nodes.get(key)
            if node is not None:
                node.set_label(row_text(prefix + suffix))
