"""Apply or reject one agent proposal after human review."""

from __future__ import annotations

from typing import Any

from ..core.entities import Milestone, Plan, Task
from ..store import Store
from . import plan_apply, plan_document
from .planning import create_task


def apply_proposal(store: Store, proposal_id: int, *, actor: str = "human") -> dict[str, Any]:
    """Apply one pending proposal atomically, then mark it applied."""
    proposal = _pending(store, proposal_id)
    handler = _APPLY_KINDS.get(str(proposal["kind"]))
    if handler is None:
        raise ValueError(f"unknown proposal kind {proposal['kind']!r}")
    result = handler(store, proposal["payload"], actor)
    store.resolve_proposal(proposal_id, "applied", actor=actor)
    return result


def _pending(store: Store, proposal_id: int) -> dict[str, Any]:
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise KeyError(f"proposal #{proposal_id} not found")
    if proposal["status"] != "pending":
        raise ValueError(f"proposal #{proposal_id} is already {proposal['status']}")
    return proposal


def _apply_plan_document(store: Store, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    document = payload.get("document")
    if not isinstance(document, dict):
        raise ValueError("plan proposal has no document object")
    parsed = plan_document.validate_document(store, document)
    return plan_apply.apply(store, parsed, actor=actor)


def _apply_row_edit(store: Store, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    row_kind = str(payload.get("kind") or "")
    row_id = int(payload.get("id") or 0)
    updater = _ROW_UPDATERS.get(row_kind)
    if updater is None:
        raise ValueError("row proposal kind must be plan, milestone, or task")
    updated = updater(
        store,
        row_id,
        str(payload.get("title") or "") or None,
        str(payload.get("desc") or "") or None,
        payload,
        actor,
    )
    if updated is None:
        raise KeyError(f"{row_kind} {row_id} not found")
    return {"kind": row_kind, "id": row_id}


def _apply_task_create(store: Store, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    task = create_task(
        store,
        int(payload.get("milestone") or 0),
        str(payload.get("title") or ""),
        description=str(payload.get("desc") or ""),
        actor=actor,
        reason="agent proposal",
    )
    return {"task": task.id, "milestone": task.milestone_id}


def _update_plan(
    store: Store,
    row_id: int,
    title: str | None,
    desc: str | None,
    payload: dict[str, Any],
    actor: str,
) -> Plan | None:
    return store.update_plan(
        row_id,
        name=title,
        description=desc,
        goal=str(payload.get("why") or "") or None,
        actor=actor,
        reason=str(payload.get("reason") or ""),
    )


def _update_milestone(
    store: Store,
    row_id: int,
    title: str | None,
    desc: str | None,
    payload: dict[str, Any],
    actor: str,
) -> Milestone | None:
    return store.update_milestone(
        row_id,
        title=title,
        description=desc,
        actor=actor,
        reason=str(payload.get("reason") or ""),
    )


def _update_task(
    store: Store,
    row_id: int,
    title: str | None,
    desc: str | None,
    payload: dict[str, Any],
    actor: str,
) -> Task | None:
    return store.update_task(
        row_id,
        title=title,
        description=desc,
        actor=actor,
        reason=str(payload.get("reason") or ""),
    )


_APPLY_KINDS = {
    "plan_document": _apply_plan_document,
    "row_edit": _apply_row_edit,
    "task_create": _apply_task_create,
}

_ROW_UPDATERS = {
    "plan": _update_plan,
    "milestone": _update_milestone,
    "task": _update_task,
}


def reject_proposal(store: Store, proposal_id: int, *, actor: str = "human") -> dict[str, Any]:
    """Reject one pending proposal without touching plan rows."""
    return store.resolve_proposal(proposal_id, "rejected", actor=actor)
