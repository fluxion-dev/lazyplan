"""Legacy session history: ids only. History is read-only."""

from __future__ import annotations


def parse_session_id(text: str) -> int:
    """Parse ``S12``, ``s12``, or ``12`` into a positive session id."""
    raw = str(text).strip()
    if raw[:1].lower() == "s":
        raw = raw[1:]
    if not raw.isdigit() or int(raw) <= 0:
        raise ValueError(f"invalid session id {text!r}; use S12 or 12")
    return int(raw)
