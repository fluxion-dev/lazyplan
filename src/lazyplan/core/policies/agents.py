"""Agent registry rules: statuses, transitions, identity, and ids.

The registry is authoritative: a row changes only through an allowed
transition, and every applied event writes one history row. Nothing here
guesses where an agent works; unbound rows carry a reason instead.
"""

from __future__ import annotations

STATUSES = (
    "starting",
    "working",
    "waiting",
    "tool",
    "compacting",
    "blocked",
    "lost",
    "ended",
)

#: Allowed moves between statuses. A repeated status is an idempotent event.
TRANSITIONS: dict[str, frozenset[str]] = {
    "starting": frozenset({"working", "waiting", "tool", "compacting", "blocked", "lost", "ended"}),
    "working": frozenset({"waiting", "tool", "compacting", "blocked", "lost", "ended"}),
    "waiting": frozenset({"working", "tool", "compacting", "blocked", "lost", "ended"}),
    "tool": frozenset({"working", "waiting", "compacting", "blocked", "lost", "ended"}),
    "compacting": frozenset({"working", "waiting", "tool", "blocked", "lost", "ended"}),
    "blocked": frozenset({"working", "waiting", "tool", "compacting", "lost", "ended"}),
    "lost": frozenset({"ended"}),
    "ended": frozenset(),
}

EVENTS = (
    "session-start",
    "prompt-submit",
    "pre-tool",
    "post-tool",
    "stop",
    "session-end",
    "pre-compact",
)

#: Canonical status after each host lifecycle event.
EVENT_STATUS: dict[str, str] = {
    "session-start": "starting",
    "prompt-submit": "working",
    "pre-tool": "tool",
    "post-tool": "working",
    "stop": "waiting",
    "session-end": "ended",
    "pre-compact": "compacting",
}

UNKNOWN = "unknown"
ROLES = ("primary", "subagent")
DEFAULT_ROLE = "primary"
NAME_LIMIT = 64
SESSION_LIMIT = 128
PATH_LIMIT = 4096


def normalize_status(text: str) -> str:
    """Return one of the known statuses, rejecting anything else."""
    body = str(text).strip().lower()
    if body not in STATUSES:
        raise ValueError(f"agent status must be {'|'.join(STATUSES)}")
    return body


def normalize_role(text: str) -> str:
    """Return ``primary`` or ``subagent``; anything else means primary."""
    body = str(text).strip().lower()
    return body if body in ROLES else DEFAULT_ROLE


def can_transition(current: str, target: str) -> bool:
    """True when one status may move to another; repeats are idempotent."""
    if current == target:
        return True
    return normalize_status(target) in TRANSITIONS.get(normalize_status(current), frozenset())


def status_for_event(event: str) -> str:
    """Canonical status for one host event, ``working`` for unknown events."""
    return EVENT_STATUS.get(str(event).strip(), "working")


def normalize_name(value: object) -> str:
    """A bounded identity value; an empty or odd value becomes ``unknown``."""
    text = str(value or "").strip()
    return text[:NAME_LIMIT] if text else UNKNOWN


def normalize_session_id(value: object) -> str:
    """A bounded host session id, or an empty string when the host has none."""
    return str(value or "").strip()[:SESSION_LIMIT]


def normalize_path(value: object) -> str:
    """A bounded path string, or an empty string."""
    return str(value or "").strip()[:PATH_LIMIT]


def parse_pid(value: object) -> int:
    """A non-negative process id, or zero when the host could not report one."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
