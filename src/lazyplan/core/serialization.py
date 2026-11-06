"""Pure entity serialization shared by every presentation surface."""

from __future__ import annotations

from .entities import PlanRevision, Status


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


def approval_payload(revision: PlanRevision | None, drift: int) -> dict:
    """Approval state for one plan: latest revision, policy, and drift."""
    if revision is None:
        return {"revision": 0, "enforced": False, "drift": drift}
    return {
        "revision": revision.revision,
        "approved_at": revision.approved_at,
        "actor": revision.actor,
        "reason": revision.reason,
        "enforced": revision.enforced,
        "drift": drift,
    }
