"""Lease and blocked-work rules: TTL parsing, expiry, and validation."""

from __future__ import annotations

import fnmatch
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


_WILDCARDS = set("*?[")


def normalize_touchpoint(text: str) -> str:
    """Normalize a repo-relative path or glob; reject escaping inputs."""
    raw = str(text).strip().replace("\\", "/")
    if not raw:
        raise ValueError("touch-point path must not be empty")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("touch-point path must be repo-relative")
    if any(ord(char) < 32 for char in raw):
        raise ValueError("touch-point path must not contain control characters")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError("touch-point path must not escape the repo")
    pattern = "/".join(parts)
    if not pattern:
        raise ValueError("touch-point path must not be empty")
    return pattern


def _static_prefix(pattern: str) -> str:
    """Path before the first wildcard, trimmed to a directory boundary."""
    index = min((pattern.find(char) for char in _WILDCARDS if char in pattern), default=-1)
    if index < 0:
        return pattern
    head = pattern[:index]
    return head.rsplit("/", 1)[0] if "/" in head else ""


def matches_path(pattern: str, path: str) -> bool:
    """True when a touch-point pattern covers a repo-relative path."""
    good = normalize_touchpoint(path)
    if any(char in pattern for char in _WILDCARDS):
        return fnmatch.fnmatchcase(good, pattern)
    return good == pattern or good.startswith(pattern + "/")


def patterns_overlap(left: str, right: str) -> bool:
    """True when two touch-point patterns can cover the same path."""
    first = _static_prefix(left)
    second = _static_prefix(right)
    if any(char in left for char in _WILDCARDS) or any(char in right for char in _WILDCARDS):
        return (
            first == second
            or not first
            or not second
            or first.startswith(second + "/")
            or second.startswith(first + "/")
        )
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")


def touchpoints_overlap(left: list[str], right: list[str]) -> bool:
    """True when any two patterns overlap."""
    return any(patterns_overlap(a, b) for a in left for b in right)
