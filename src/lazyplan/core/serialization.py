"""Pure entity serialization shared by every presentation surface."""

from __future__ import annotations

from .entities import Status


def to_payload(d: dict) -> dict:
    """JSON/agent-safe: Status -> value, omit empty blocked fields."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    if not d.get("blocked"):
        d.pop("blocked", None)
    if not d.get("blocked_reason"):
        d.pop("blocked_reason", None)
    return d
