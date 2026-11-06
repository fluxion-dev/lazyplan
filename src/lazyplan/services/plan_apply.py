"""Atomic plan apply: one transaction for a validated plan document."""

from __future__ import annotations

from typing import Any

from ..core.ports.planning import PlanningPort
from .plan_document import MilestoneDocument, PlanDocument, PlanDocumentError


def _ensure_key_free(port: PlanningPort, kind: str, key: str) -> None:
    existing = port.get_entity_key(kind, key)
    if existing is not None:
        raise PlanDocumentError(f"{kind} key {key!r} already belongs to #{existing}")


def _tree_counts(port: PlanningPort, plan_id: int) -> dict[str, int]:
    milestones = port.list_milestones(plan_id)
    tasks = 0
    criteria = len(port.list_criteria("plan", plan_id))
    for milestone in milestones:
        criteria += len(port.list_criteria("milestone", milestone.id))
        for task in port.list_tasks(milestone.id):
            tasks += 1
            criteria += len(port.list_criteria("task", task.id))
    return {"milestones": len(milestones), "tasks": tasks, "criteria": criteria}


def _create_milestone(
    port: PlanningPort,
    plan_id: int,
    milestone: MilestoneDocument,
    actor: str,
    counts: dict[str, int],
) -> None:
    _ensure_key_free(port, "milestone", milestone.key)
    row = port.add_milestone(
        plan_id,
        milestone.title,
        milestone.description,
        actor=actor,
    )
    port.set_entity_key("milestone", row.id, milestone.key, actor=actor)
    for text in milestone.criteria:
        port.add_criteria("milestone", row.id, text, actor=actor)
        counts["criteria"] += 1
    counts["milestones"] += 1
    for task in milestone.tasks:
        _ensure_key_free(port, "task", task.key)
        created = port.add_task(
            row.id,
            task.title,
            task.description,
            actor=actor,
        )
        port.set_entity_key("task", created.id, task.key, actor=actor)
        for text in task.criteria:
            port.add_criteria("task", created.id, text, actor=actor)
            counts["criteria"] += 1
        counts["tasks"] += 1


def apply(port: PlanningPort, document: PlanDocument, actor: str = "human") -> dict[str, Any]:
    """Create a validated document atomically; an identical retry is a no-op."""
    existing = port.get_entity_key("plan", document.key)
    if existing is not None:
        plan = port.get_plan(existing)
        if plan is None:
            raise PlanDocumentError(f"plan key {document.key!r} points at missing row #{existing}")
        return {"plan": plan, "created": False, "counts": _tree_counts(port, plan.id)}

    counts = {"milestones": 0, "tasks": 0, "criteria": 0}
    with port.transaction():
        _ensure_key_free(port, "plan", document.key)
        plan = port.add_plan(
            document.title,
            description=document.what,
            goal=document.why,
            actor=actor,
        )
        port.set_entity_key("plan", plan.id, document.key, actor=actor)
        for text in document.criteria:
            port.add_criteria("plan", plan.id, text, actor=actor)
            counts["criteria"] += 1
        for milestone in document.milestones:
            _create_milestone(port, plan.id, milestone, actor, counts)
    return {"plan": plan, "created": True, "counts": counts}
