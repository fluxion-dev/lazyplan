"""Pure entity serialization shared by every presentation surface."""

from __future__ import annotations

from collections.abc import Sequence

from .entities import PlanChange, PlanRevision, Status


def to_payload(d: dict) -> dict:
    """JSON/agent-safe: Status -> value, omit empty blocked and archive fields."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    if not d.get("blocked"):
        d.pop("blocked", None)
    if not d.get("blocked_reason"):
        d.pop("blocked_reason", None)
    if not d.get("archived_at"):
        d.pop("archived_at", None)
    return d


def approval_payload(
    revision: PlanRevision | None,
    drift: int,
    recent: Sequence[PlanChange] | None = None,
) -> dict:
    """Approval state for one plan: latest revision, policy, drift, and recent changes."""
    if revision is None:
        return {"revision": 0, "enforced": False, "drift": drift}
    payload = {
        "revision": revision.revision,
        "approved_at": revision.approved_at,
        "actor": revision.actor,
        "reason": revision.reason,
        "enforced": revision.enforced,
        "drift": drift,
    }
    if recent is not None:
        payload["recent"] = [
            {
                "kind": change.kind,
                "action": change.action,
                "field": change.field,
                "reason": change.reason,
                "actor": change.actor,
            }
            for change in recent
        ]
    return payload
