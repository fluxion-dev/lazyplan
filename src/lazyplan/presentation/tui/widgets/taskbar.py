"""Bottom taskbar: key hints on the left, health and version on the right.

The badge reflects the running version and, when the update cache knows a
newer release, adds an arrow to it. Clicking the badge runs the app's update
action; it never checks the network itself.
"""

from __future__ import annotations

from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import Static

from ....infrastructure.environment import UpgradeError, parse_version
from ...shared.design import escape_markup

VERSION_GAP = "  "


def version_text(running: str, latest: str = "") -> str:
    """Format the running version, adding a newer cached release when known."""
    current = running.strip().lstrip("vV")
    if not current:
        return ""
    label = f"v{current}"
    candidate = latest.strip().lstrip("vV")
    if not candidate:
        return label
    try:
        if parse_version(candidate) <= parse_version(current):
            return label
    except UpgradeError:
        return label
    return f"{label} → v{candidate}"


def badge_markup(text: str) -> str:
    """The badge text; the taskbar handles its click."""
    return escape_markup(text) if text else ""


def _right_markup(health: str, running: str, latest: str) -> str:
    """Health first, then the version badge, joined by the shared gap."""
    return VERSION_GAP.join(
        part for part in (health, badge_markup(version_text(running, latest))) if part
    )


def badge_start(
    *,
    health: str = "",
    running: str = "",
    latest: str = "",
    width: int = 80,
) -> int:
    """The column where the clickable badge begins."""
    right = _right_markup(health, running, latest)
    if not right:
        return 0
    return max(0, width - Content.from_markup(right).cell_length)


def taskbar_markup(
    hints: str,
    *,
    health: str = "",
    running: str = "",
    latest: str = "",
    width: int = 80,
) -> str:
    """Compose one right-aligned taskbar line within *width* columns."""
    right = _right_markup(health, running, latest)
    if not right:
        return hints
    right_len = Content.from_markup(right).cell_length
    left = hints
    if Content.from_markup(left).cell_length + right_len + 1 > width:
        left = _truncate_hints(left, max(8, width - right_len - 2))
    gap = max(1, width - Content.from_markup(left).cell_length - right_len)
    return left + (" " * gap) + right


def _truncate_hints(hints: str, width: int) -> str:
    """Drop trailing hint items until the markup fits *width* columns."""
    parts = hints.split(" · ")
    while len(parts) > 1 and Content.from_markup(" · ".join(parts)).cell_length > width:
        parts.pop()
    return " · ".join(parts)


class Taskbar(Static):
    """One-line bar that keeps its badge pinned to the right edge."""

    def __init__(self, content: str = "", **kwargs: Any) -> None:
        self._hints = ""
        self._health = ""
        self._version_running = ""
        self._version_latest = ""
        self._badge_start = 0
        super().__init__(content, markup=True, **kwargs)

    def set_line(
        self,
        hints: str,
        *,
        health: str = "",
        running: str = "",
        latest: str = "",
    ) -> None:
        """Remember the line and repaint it at the current widget width."""
        if not running:
            from ...cli.parser import package_version

            running = package_version()
        self._hints = hints
        self._health = health
        self._version_running = running
        self._version_latest = latest
        self._repaint()

    def set_for_app(self, hints: str, *, health: str = "") -> None:
        """Repaint from the app's remembered update state."""
        controller = getattr(self.app, "update_controller", None)
        self.set_line(hints, health=health, latest=str(getattr(controller, "latest", "") or ""))

    def set_latest(self, latest: str) -> None:
        """Repaint after an update poll names or clears a newer release."""
        self._version_latest = latest
        self._repaint()

    def on_resize(self) -> None:
        """Keep the badge pinned after a terminal resize."""
        self._repaint()

    def on_click(self, event: events.Click) -> None:
        """Open updates when the click lands on the version badge."""
        if self._badge_start and event.x >= self._badge_start:
            event.stop()
            self.app.action_update_prompt()  # type: ignore[attr-defined]

    def _repaint(self) -> None:
        width = max(10, self.size.width or 80)
        self._badge_start = badge_start(
            health=self._health,
            running=self._version_running,
            latest=self._version_latest,
            width=width,
        )
        self.update(
            taskbar_markup(
                self._hints,
                health=self._health,
                running=self._version_running,
                latest=self._version_latest,
                width=width,
            )
        )
