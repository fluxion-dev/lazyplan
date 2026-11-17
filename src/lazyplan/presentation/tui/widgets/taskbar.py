"""Bottom taskbar: key hints on the left, log, health, and version on the right.

The version badge reflects the running version and, when the update cache knows
a newer release, adds an arrow to it. Clicking the badge runs the app's update
action; it never checks the network itself. The log chip names the unread
warning and error count and opens the notification log when clicked.
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


def log_chip(count: int) -> str:
    """The unread warning/error chip; information-only logs show nothing."""
    if count <= 0:
        return ""
    return f"[reverse] log [/]{count}"


def _right_markup(health: str, running: str, latest: str, log: str = "") -> str:
    """Log chip, health, then the version badge, joined by the shared gap."""
    return VERSION_GAP.join(
        part for part in (log, health, badge_markup(version_text(running, latest))) if part
    )


def badge_start(
    *,
    health: str = "",
    running: str = "",
    latest: str = "",
    log: str = "",
    width: int = 80,
) -> int:
    """The column where the clickable version badge begins."""
    right = _right_markup(health, running, latest, log)
    if not right:
        return 0
    return max(0, width - Content.from_markup(right).cell_length)


def log_span(
    *,
    log: str = "",
    health: str = "",
    running: str = "",
    latest: str = "",
    width: int = 80,
) -> tuple[int, int]:
    """The half-open column span of the clickable log chip."""
    if not log:
        return (0, 0)
    right = _right_markup(health, running, latest, log)
    start = max(0, width - Content.from_markup(right).cell_length)
    return (start, start + Content.from_markup(log).cell_length)


def taskbar_markup(
    hints: str,
    *,
    health: str = "",
    running: str = "",
    latest: str = "",
    log: str = "",
    width: int = 80,
) -> str:
    """Compose one right-aligned taskbar line within *width* columns."""
    right = _right_markup(health, running, latest, log)
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


def _unread_for_app(app: Any) -> int:
    """The app's unread warning/error count, or zero without a log."""
    log = getattr(app, "notification_log", None)
    try:
        return max(0, int(getattr(log, "unread", 0) or 0))
    except (TypeError, ValueError):
        return 0


class Taskbar(Static):
    """One-line bar that keeps its badge pinned to the right edge."""

    def __init__(self, content: str = "", **kwargs: Any) -> None:
        self._hints = ""
        self._health = ""
        self._version_running = ""
        self._version_latest = ""
        self._log_count = 0
        self._badge_start = 0
        self._log_start = 0
        self._log_end = 0
        super().__init__(content, markup=True, **kwargs)

    @property
    def log_count(self) -> int:
        """The unread warning/error count the chip shows."""
        return self._log_count

    def set_line(
        self,
        hints: str,
        *,
        health: str = "",
        running: str = "",
        latest: str = "",
        log_count: int | None = None,
    ) -> None:
        """Remember the line and repaint it at the current widget width."""
        if not running:
            from ...cli.parser import package_version

            running = package_version()
        self._hints = hints
        self._health = health
        self._version_running = running
        self._version_latest = latest
        if log_count is not None:
            self._log_count = max(0, log_count)
        self._repaint()

    def set_for_app(self, hints: str, *, health: str = "") -> None:
        """Repaint from the app's remembered update and log state."""
        controller = getattr(self.app, "update_controller", None)
        self.set_line(
            hints,
            health=health,
            latest=str(getattr(controller, "latest", "") or ""),
            log_count=_unread_for_app(self.app),
        )

    def set_latest(self, latest: str) -> None:
        """Repaint after an update poll names or clears a newer release."""
        self._version_latest = latest
        self._repaint()

    def set_log_count(self, count: int) -> None:
        """Repaint after the notification log gains unread warnings or clear."""
        self._log_count = max(0, count)
        self._repaint()

    def on_resize(self) -> None:
        """Keep the badge pinned after a terminal resize."""
        self._repaint()

    def on_click(self, event: events.Click) -> None:
        """Open the log on the log chip and updates on the version badge."""
        if self._log_end > self._log_start and self._log_start <= event.x < self._log_end:
            event.stop()
            handler = getattr(self.app, "action_notification_log", None)
            if callable(handler):
                handler()
            return
        if self._badge_start and event.x >= self._badge_start:
            event.stop()
            self.app.action_update_prompt()  # type: ignore[attr-defined]

    def _repaint(self) -> None:
        width = max(10, self.size.width or 80)
        log = log_chip(self._log_count)
        self._log_start, self._log_end = log_span(
            log=log,
            health=self._health,
            running=self._version_running,
            latest=self._version_latest,
            width=width,
        )
        self._badge_start = badge_start(
            health=self._health,
            running=self._version_running,
            latest=self._version_latest,
            log=log,
            width=width,
        )
        self.update(
            taskbar_markup(
                self._hints,
                health=self._health,
                running=self._version_running,
                latest=self._version_latest,
                log=log,
                width=width,
            )
        )
