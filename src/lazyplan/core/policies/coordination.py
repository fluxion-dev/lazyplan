"""Lease and blocked-work rules: TTL parsing, expiry, and validation."""

from __future__ import annotations

import re

from ..entities import Status, Task

#: Default lease length in seconds.
CLAIM_DEFAULT_TTL = 30 * 60

_TTL_UNITS = {
    None: 1,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}
_TTL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\.?\s*([a-z]+)?\s*$", re.IGNORECASE)


def parse_ttl(text: str | None, default: float = CLAIM_DEFAULT_TTL) -> float:
    """Parse a lease TTL such as `30m`, `2.hours`, `90s`, or `1.days`."""
    if not text:
        return float(default)
    match = _TTL_RE.match(text)
    if match is None:
        raise ValueError(f"invalid ttl {text!r}; use 30m, 2.hours, or seconds")
    unit = (match.group(2) or "s").lower()
    if unit not in _TTL_UNITS:
        raise ValueError(f"unknown ttl unit {unit!r}; use s, m, h, d, or w")
    seconds = float(match.group(1)) * _TTL_UNITS[unit]
    if seconds <= 0:
        raise ValueError("claim ttl must be positive")
    return seconds


def validate_block(task: Task, reason: str) -> None:
    """Reject a block that cannot become a parked task."""
    if task.status == Status.DONE:
        raise ValueError("cannot block a done task")
    if not reason.strip():
        raise ValueError("blocking a task needs a reason")
