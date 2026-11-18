"""App-wide notification routing: every message logs; two notices may toast.

The log is the only destination for ordinary messages, so controllers,
screens, and widgets call ``notify`` and never reach a Textual toast. Only the
startup notice and the once-per-version update announcement call
``notify_toast``; that helper logs through the same path and then raises the
single toast this app allows.
"""

from __future__ import annotations

try:
    from textual.app import SeverityLevel
    from textual.message import Message

    from .base import AppBase
    from .controllers.notifications import NotificationLog

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class NotificationsChanged(Message):
        """A notification joined the log; bars and an open log may repaint."""

    class NotificationMixin(AppBase):
        """Route every notification into the log and repaint on arrival."""

        notification_log: NotificationLog

        def notify(
            self,
            message: str,
            *,
            title: str = "",
            severity: SeverityLevel = "information",
            timeout: float | None = None,
            markup: bool = True,
            source: str = "",
        ) -> None:
            """Log every message; ordinary notices never raise a toast."""
            self.notification_log.append(
                message,
                severity=severity,
                source=source or self._notification_source(),
            )
            self.post_message(NotificationsChanged())

        def notify_toast(
            self,
            message: str,
            *,
            title: str = "",
            severity: SeverityLevel = "information",
            timeout: float | None = None,
            markup: bool = True,
            source: str = "",
        ) -> None:
            """Log the message and toast it; startup and update notices only."""
            self.notify(message, severity=severity, source=source)
            super().notify(
                message,
                title=title,
                severity=severity,
                timeout=timeout,
                markup=markup,
            )

        def _notification_source(self) -> str:
            """The active screen's name, so every entry says where it came from."""
            try:
                screen = self.screen
            except Exception:  # noqa: BLE001 - a closing screen may race a worker
                return "tree"
            named = str(getattr(screen, "navigation_name", "") or "")
            if named:
                return named
            class_name = type(screen).__name__.removesuffix("Screen")
            return class_name.lower() or "tree"

        def on_notifications_changed(self, _event: NotificationsChanged) -> None:
            """Repaint every bar and an open log when a message arrives."""
            self.refresh_taskbar()
            try:
                refresh = getattr(self.screen, "refresh_entries", None)
            except Exception:  # noqa: BLE001 - a closing screen may race a worker
                return
            if callable(refresh):
                refresh()
