"""Bounded, session-only notification log shared by every TUI surface.

The log is a plain model: no Textual imports, no widget access, and no
persistence. Workers may append to it directly, so every read and write takes
one lock. Warning and error entries raise an unread count until the log is
opened; information entries never badge.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

CAPACITY = 500

#: Severities that raise the taskbar's unread chip.
BADGE_SEVERITIES = frozenset({"warning", "error"})


@dataclass(frozen=True)
class NotificationEntry:
    """One captured notification, kept for the life of the session."""

    at: float
    severity: str
    message: str
    source: str = ""

    @property
    def clock(self) -> str:
        """Local wall-clock time, to the second."""
        return time.strftime("%H:%M:%S", time.localtime(self.at))

    def text(self) -> str:
        """One plain line: clock, severity, message, then the source."""
        line = f"{self.clock}  {self.severity:<11}  {self.message}"
        return f"{line}  ({self.source})" if self.source else line


class NotificationLog:
    """The last *capacity* entries plus the unread warning/error count."""

    def __init__(
        self,
        capacity: int = CAPACITY,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._entries: deque[NotificationEntry] = deque(maxlen=max(1, capacity))
        self._clock = clock
        self._unread = 0
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        """How many entries the log keeps."""
        return self._entries.maxlen or 0

    def append(
        self,
        message: str,
        *,
        severity: str = "information",
        source: str = "",
    ) -> NotificationEntry:
        """Record one message and return the stored entry."""
        entry = NotificationEntry(
            at=self._clock(),
            severity=severity,
            message=str(message),
            source=source,
        )
        with self._lock:
            self._entries.append(entry)
            if severity in BADGE_SEVERITIES:
                self._unread += 1
        return entry

    @property
    def unread(self) -> int:
        """Unread warning and error entries; information never counts."""
        with self._lock:
            return self._unread

    def mark_read(self) -> None:
        """Clear the badge without dropping any entry."""
        with self._lock:
            self._unread = 0

    def clear(self) -> None:
        """Drop every entry and the badge."""
        with self._lock:
            self._entries.clear()
            self._unread = 0

    def snapshot(self) -> tuple[NotificationEntry, ...]:
        """Every entry, oldest first, as an immutable copy."""
        with self._lock:
            return tuple(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
