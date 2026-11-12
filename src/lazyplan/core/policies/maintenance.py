"""Maintenance rules: archive windows, archive candidates, and trim predicates.

Every window defaults to one week. The rules are pure: the caller supplies the
clock, the status-event map, and the row lists.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from ..entities import Claim, Plan, Session, Status

#: One window for done plans, ended sessions, and old events.
DEFAULT_WINDOW_DAYS = 7.0
DEFAULT_WINDOW_SECS = DEFAULT_WINDOW_DAYS * 86400

#: The three archive views every read surface understands.
ARCHIVE_MODES = ("hide", "only", "show")

_DAYS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*\.?\s*([a-z]+)?\s*$", re.IGNORECASE)
_DAY_UNITS = {
    None: 1.0,
    "d": 1.0,
    "day": 1.0,
    "days": 1.0,
    "w": 7.0,
    "week": 7.0,
    "weeks": 7.0,
}


def parse_window_days(text: str | None, default: float = DEFAULT_WINDOW_DAYS) -> float:
    """Parse ``7.days``, ``30.days``, or a bare day count into days."""
    if text is None or not str(text).strip():
        return float(default)
    match = _DAYS_RE.match(str(text))
    if match is None:
        raise ValueError(f"invalid window {text!r}; use 7.days, 30.days, or a day count")
    unit = (match.group(2) or "d").lower()
    if unit not in _DAY_UNITS:
        raise ValueError(f"unknown window unit {unit!r}; use d, day, days, w, week, or weeks")
    days = float(match.group(1)) * _DAY_UNITS[unit]
    if days <= 0:
        raise ValueError("maintenance window must be positive")
    return days


def parse_window_secs(text: str | None, default: float = DEFAULT_WINDOW_DAYS) -> float:
    """Parse a window into seconds, using the one-week default when empty."""
    return parse_window_days(text, default=default) * 86400


def check_archive_mode(mode: str) -> str:
    """Validate one archive view and return it unchanged."""
    if mode not in ARCHIVE_MODES:
        raise ValueError("archived must be hide|only|show")
    return mode


def is_archived_row(row: object) -> bool:
    """True when a plan or session carries an archive stamp."""
    return float(getattr(row, "archived_at", 0.0) or 0.0) > 0.0


def is_visible(row: object, archived: str = "hide") -> bool:
    """True when one row survives the archive view (hide, only, or show)."""
    check_archive_mode(archived)
    if archived == "show":
        return True
    return is_archived_row(row) == (archived == "only")


def visible_rows(rows: Iterable[object], archived: str = "hide") -> list[object]:
    """Filter rows by the archive view: hide, only, or show."""
    if archived == "show":
        return list(rows)
    return [row for row in rows if is_visible(row, archived)]


def plan_done_at(events: Mapping[int, tuple[float, str]], plan_id: int) -> float | None:
    """Timestamp of the plan's latest done transition, or None."""
    last = events.get(plan_id)
    if last is None:
        return None
    timestamp, target = last
    return float(timestamp) if target == Status.DONE.value else None


def is_done_past_window(
    plan: Plan,
    events: Mapping[int, tuple[float, str]],
    now: float,
    window_secs: float = DEFAULT_WINDOW_SECS,
) -> bool:
    """True when a plan has held done longer than the window."""
    if plan.status != Status.DONE:
        return False
    done_at = plan_done_at(events, plan.id)
    return done_at is not None and (now - done_at) > window_secs


def is_ended_past_window(
    session: Session,
    now: float,
    window_secs: float = DEFAULT_WINDOW_SECS,
) -> bool:
    """True when an ended session closed longer ago than the window."""
    if not session.ended:
        return False
    return (now - session.ended_at) > window_secs


def is_expired_claim(claim: Claim, now: float) -> bool:
    """True when a lease has lapsed and can be trimmed."""
    return claim.expired(now)


def event_cutoff(now: float, window_secs: float = DEFAULT_WINDOW_SECS) -> float:
    """Events older than this timestamp can be trimmed."""
    return now - window_secs


def is_old_event(event: Mapping[str, object], cutoff: float) -> bool:
    """True when one event row predates the cutoff; untimed rows are kept."""
    raw = event.get("ts")
    if raw is None:
        return False
    try:
        stamp = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return stamp < cutoff


def plan_archive_candidates(
    plans: Sequence[Plan],
    events: Mapping[int, tuple[float, str]],
    now: float,
    window_secs: float = DEFAULT_WINDOW_SECS,
) -> list[Plan]:
    """Done plans past the window that are not archived yet."""
    return [
        plan
        for plan in plans
        if not is_archived_row(plan) and is_done_past_window(plan, events, now, window_secs)
    ]


def session_archive_candidates(
    sessions: Sequence[Session],
    now: float,
    window_secs: float = DEFAULT_WINDOW_SECS,
) -> list[Session]:
    """Ended sessions past the window that are not archived yet."""
    return [
        session
        for session in sessions
        if not is_archived_row(session) and is_ended_past_window(session, now, window_secs)
    ]
