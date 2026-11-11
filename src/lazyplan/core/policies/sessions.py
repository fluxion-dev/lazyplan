"""Session rules: identity, lifecycle, summaries, and handoff limits."""

from __future__ import annotations

SUMMARY_LIMIT = 4000
HANDOFF_LIMIT = 2000
PHASES = ("working", "awaiting")
PLAN_SOURCES = ("auto", "manual")

#: An open session with no heartbeat for this long is stale in the UI.
STALE_AFTER_SECS = 15 * 60

#: An open session with no heartbeat for this long is safe to close.
IDLE_AFTER_SECS = 2 * 3600


def normalize_phase(text: str) -> str:
    """Return one of ``working`` or ``awaiting``, rejecting anything else."""
    body = str(text).strip().lower()
    if body not in PHASES:
        raise ValueError(f"session phase must be {'|'.join(PHASES)}")
    return body


def phase_for_event(event: str) -> str:
    """Canonical phase after a hook event: stop waits on the user."""
    return "awaiting" if event == "stop" else "working"


def normalize_plan_source(text: str) -> str:
    """Return ``auto`` or ``manual`` for how a session got its plan."""
    body = str(text).strip().lower()
    if body not in PLAN_SOURCES:
        raise ValueError(f"session plan source must be {'|'.join(PLAN_SOURCES)}")
    return body


def auto_close_summary(seconds: float) -> str:
    """Summary recorded when idle reaping closes an abandoned session."""
    hours = max(1, round(max(seconds, 0.0) / 3600))
    return f"auto-closed after {hours}h idle"


def parse_session_id(text: str) -> int:
    """Parse ``S12``, ``s12``, or ``12`` into a positive session id."""
    raw = str(text).strip()
    if raw[:1].lower() == "s":
        raw = raw[1:]
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"invalid session id {text!r}; use S12 or 12")
    return int(raw)


def normalize_summary(text: str) -> str:
    """Trimmed summary; an empty summary is allowed."""
    body = str(text).strip()
    if len(body) > SUMMARY_LIMIT:
        raise ValueError(f"session summary must be at most {SUMMARY_LIMIT} characters")
    return body


def normalize_handoff(text: str) -> str:
    """Trimmed handoff note; an empty handoff is allowed."""
    body = str(text).strip()
    if len(body) > HANDOFF_LIMIT:
        raise ValueError(f"session handoff must be at most {HANDOFF_LIMIT} characters")
    return body


def supersede_summary(previous_id: int, new_id: int) -> str:
    """Summary recorded when a session is force-replaced by a newer one."""
    return f"superseded by session S{new_id}" if new_id else f"superseded session S{previous_id}"
