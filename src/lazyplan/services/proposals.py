"""Apply or reject one agent proposal after human review."""

from __future__ import annotations

from typing import Any

from ..core.entities import Milestone, Plan, Task
from ..store import Store
from . import plan_apply, plan_document
from .planning import create_task


def apply_proposal(store: Store, proposal_id: int, *, actor: str = "human") -> dict[str, Any]:
    """Apply one pending proposal atomically, then mark it applied."""
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"proposal #{proposal_id} not found")
    if proposal["status"] != "pending":
        raise ValueError(f"proposal #{proposal_id} is already {proposal['status']}")
    payload = proposal["payload"]
    kind = proposal["kind"]
    result: dict[str, Any]
    if kind == "plan_document":
        document = payload.get("document")
        if not isinstance(document, dict):
            raise ValueError("plan proposal has no document object")
        parsed = plan_document.validate_document(store, document)
        result = plan_apply.apply(store, parsed, actor=actor)
    elif kind == "row_edit":
        row_kind = str(payload.get("kind") or "")
        row_id = int(payload.get("id") or 0)
        title = str(payload.get("title") or "") or None
        desc = str(payload.get("desc") or "") or None
        reason = str(payload.get("reason") or "")
        updated: Plan | Milestone | Task | None
        if row_kind == "plan":
            updated = store.update_plan(
                row_id,
                name=title,
                description=desc,
                goal=str(payload.get("why") or "") or None,
                actor=actor,
                reason=reason,
            )
        elif row_kind == "milestone":
            updated = store.update_milestone(
                row_id, title=title, description=desc, actor=actor, reason=reason
            )
        elif row_kind == "task":
            updated = store.update_task(
                row_id, title=title, description=desc, actor=actor, reason=reason
            )
        else:
            raise ValueError("row proposal kind must be plan, milestone, or task")
        if updated is None:
            raise KeyError(f"{row_kind} {row_id} not found")
        result = {"kind": row_kind, "id": row_id}
    elif kind == "task_create":
        task = create_task(
            store,
            int(payload.get("milestone") or 0),
            str(payload.get("title") or ""),
            description=str(payload.get("desc") or ""),
            actor=actor,
            reason="agent proposal",
        )
        result = {"task": task.id, "milestone": task.milestone_id}
    else:
        raise ValueError(f"unknown proposal kind {kind!r}")
    store.resolve_proposal(proposal_id, "applied", actor=actor)
    return result


def reject_proposal(store: Store, proposal_id: int, *, actor: str = "human") -> dict[str, Any]:
    """Reject one pending proposal without touching plan rows."""
    return store.resolve_proposal(proposal_id, "rejected", actor=actor)
