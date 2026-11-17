"""Planning use cases: plans, milestones, tasks, criteria, status, and trees."""

from __future__ import annotations

import time

from lazyplan.infrastructure.templates import apply_template, template_criteria

from ..core.entities import Milestone, Plan, Status, Task
from ..core.kinds import check_kind
from ..core.policies.lanes import (
    DEFAULT_AGENT_ROLE,
    DEFAULT_DISPATCH_MODE,
    DEFAULT_LANE_GROUP,
    DEFAULT_MAX_AGENTS,
)
from ..core.policies.planning import next_status, rollup_target
from ..core.ports.coordination import CoordinationPort
from ..core.ports.planning import PlanningPort
from .doing_claims import check_claimable, claim_for_doing
from .tree_view import (
    TreeSource as TreeSource,
)
from .tree_view import (
    _filtered_milestones as _filtered_milestones,
)
from .tree_view import (
    _is_finished as _is_finished,
)
from .tree_view import (
    _plan_activity as _plan_activity,
)
from .tree_view import (
    _plan_matches_repo as _plan_matches_repo,
)
from .tree_view import (
    _repo_match as _repo_match,
)
from .tree_view import (
    _visible_plan as _visible_plan,
)
from .tree_view import (
    activity_source as activity_source,
)
from .tree_view import (
    plan_activity as plan_activity,
)
from .tree_view import (
    tree as tree,
)

DEFAULT_PLAN_LIMIT = 5

#: Backward-compatible private alias used by the services facade.
_rollup_target = rollup_target


def create_plan(
    port: PlanningPort,
    name: str,
    description: str = "",
    goal: str = "",
    actor: str = "human",
    dispatch_mode: str = DEFAULT_DISPATCH_MODE,
    max_agents: int = DEFAULT_MAX_AGENTS,
) -> Plan:
    """Insert a plan with template defaults and auto-criteria."""
    filled = apply_template(
        "plan",
        {"title": name, "why": goal, "what": description},
        port.db_path,
    )
    plan = port.add_plan(
        name=filled["title"].strip(),
        description=filled["what"],
        goal=filled["why"],
        actor=actor,
        dispatch_mode=dispatch_mode,
        max_agents=max_agents,
    )
    for text in template_criteria("plan", port.db_path):
        port.add_criteria("plan", plan.id, text, actor=actor)
    return plan


def create_milestone(
    port: PlanningPort,
    plan_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
    reason: str = "",
    lane_group: int = DEFAULT_LANE_GROUP,
    agent_role: str = DEFAULT_AGENT_ROLE,
) -> Milestone:
    """Insert a milestone with template defaults and auto-criteria."""
    filled = apply_template(
        "milestone",
        {"title": title, "desc": description},
        port.db_path,
    )
    milestone = port.add_milestone(
        plan_id=plan_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
        reason=reason,
        lane_group=lane_group,
        agent_role=agent_role,
    )
    for text in template_criteria("milestone", port.db_path):
        port.add_criteria("milestone", milestone.id, text, actor=actor, reason=reason)
    return milestone


def create_task(
    port: PlanningPort,
    milestone_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
    reason: str = "",
    role: str = DEFAULT_AGENT_ROLE,
) -> Task:
    """Insert a task with template defaults and auto-criteria."""
    filled = apply_template(
        "task",
        {"title": title, "desc": description},
        port.db_path,
    )
    task = port.add_task(
        milestone_id=milestone_id,
        title=filled["title"].strip(),
        description=filled["desc"],
        actor=actor,
        reason=reason,
        role=role,
    )
    for text in template_criteria("task", port.db_path):
        port.add_criteria("task", task.id, text, actor=actor, reason=reason)
    return task


def heal(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    actor: str = "human",
    *,
    empty: bool = False,
) -> bool:
    """Recompute one milestone or plan from its children. Returns changed."""
    check_kind(kind)
    obj: Plan | Milestone | None
    if kind == "milestone":
        obj = port.get_milestone(obj_id)
        kids = [task.status for task in port.list_tasks(obj_id)] if obj is not None else []
    elif kind == "plan":
        obj = port.get_plan(obj_id)
        kids = [row.status for row in port.list_milestones(obj_id)] if obj is not None else []
    else:
        raise ValueError("kind must be milestone|plan")
    if obj is None or (not kids and not empty):
        return False
    target = rollup_target(kids)
    if obj.status == target:
        return False
    port.set_status_raw(kind, obj_id, target)
    port.log(actor, kind, "status", f"{kind} #{obj_id} -> {target.value} (rollup)")
    return True


def heal_parents(port: PlanningPort, kind: str, obj_id: int, actor: str = "human") -> None:
    """Recompute ancestors after a status write; childless rows keep manual status."""
    check_kind(kind)
    if kind == "task":
        task = port.get_task(obj_id)
        if task is None:
            return
        heal(port, "milestone", task.milestone_id, actor)
        milestone = port.get_milestone(task.milestone_id)
        if milestone is not None:
            heal(port, "plan", milestone.plan_id, actor)
    elif kind == "milestone":
        heal(port, "milestone", obj_id, actor)
        milestone = port.get_milestone(obj_id)
        if milestone is not None:
            heal(port, "plan", milestone.plan_id, actor)
    elif kind == "plan":
        heal(port, "plan", obj_id, actor)


def delete_row(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    actor: str = "human",
    reason: str = "",
) -> bool:
    """Delete one row, then recompute the ancestors its subtree belonged to."""
    check_kind(kind)
    milestone_id: int | None = None
    plan_id: int | None = None
    if kind == "task":
        task = port.get_task(obj_id)
        if task is not None:
            milestone_id = task.milestone_id
            milestone = port.get_milestone(milestone_id)
            plan_id = milestone.plan_id if milestone is not None else None
    elif kind == "milestone":
        milestone = port.get_milestone(obj_id)
        if milestone is not None:
            plan_id = milestone.plan_id
    ok = port.delete(kind, obj_id, actor=actor, reason=reason)
    if not ok:
        return False
    if kind == "task" and milestone_id is not None:
        heal(port, "milestone", milestone_id, actor, empty=True)
        if plan_id is not None:
            heal(port, "plan", plan_id, actor, empty=True)
    elif kind == "milestone" and plan_id is not None:
        heal(port, "plan", plan_id, actor, empty=True)
    return True


def set_status(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    status: Status,
    actor: str = "human",
    heal: bool = True,
    take_claim: bool = True,
    worktree: str = "",
    check_lane: bool = True,
) -> bool:
    """Move a row and log it; a doing task is claimed and checked against its lane.

    ``take_claim=False`` restores a recorded status (import) without claiming.
    """
    check_kind(kind)
    claim = None
    get_claim = getattr(port, "get_claim", None) if kind == "task" else None
    if get_claim is not None:
        claim = get_claim(obj_id)
    doing = take_claim and kind == "task" and status is Status.DOING
    if doing:
        check_claimable(port, claim, obj_id, actor, worktree or port.checkout_path(), check_lane)
    ok = port.set_status_raw(kind, obj_id, status)
    if ok:
        port.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        if doing:
            claim_for_doing(port, claim, obj_id, actor, worktree=worktree)
        elif claim is not None:
            port.log(actor, "task", "release", f"task #{obj_id} released by status")
        if heal:
            heal_parents(port, kind, obj_id, actor)
    return ok


def end_claim(port: PlanningPort, task_id: int, actor: str) -> None:
    """Drop a task's claim and send it back to todo if it was still doing."""
    task = port.get_task(task_id)
    if task is not None and task.status is Status.DOING:
        set_status(port, "task", task_id, Status.TODO, actor=actor)
        return
    release = getattr(port, "release_claim", None)
    if release is not None:
        release(task_id, actor, force=True)


def requeue_expired(port: CoordinationPort, now: float | None = None) -> list[int]:
    """End every expired claim; returns the task ids it requeued or released."""
    stamp = time.time() if now is None else now
    ended = []
    for claim in port.list_claims(include_expired=True, now=stamp):
        if claim["expired"]:
            end_claim(port, int(claim["task_id"]), str(claim["actor"]))
            ended.append(int(claim["task_id"]))
    return ended


def cycle_status(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    actor: str = "human",
    heal: bool = True,
) -> Status | None:
    """Advance todo to doing to done to todo."""
    check_kind(kind)
    obj = port.get_parent(kind, obj_id)
    if obj is None:
        return None
    status = next_status(obj.status)
    set_status(port, kind, obj_id, status, actor=actor, heal=heal)
    return status


def _child_rollup(port: PlanningPort, kind: str, obj_id: int) -> Status | None:
    """The status children imply, or None when the row has none."""
    if kind == "milestone":
        kids = [task.status for task in port.list_tasks(obj_id)]
    else:
        kids = [row.status for row in port.list_milestones(obj_id)]
    return rollup_target(kids) if kids else None


def reconcile(
    port: CoordinationPort,
    actor: str = "human",
    check: bool = False,
    heal_mode: bool = True,
    strict: bool = False,
) -> dict[str, list]:
    """Heal parents and leases; check mode reports without writing."""
    write = not check and heal_mode
    changes: list[dict] = []
    for plan in port.list_plans():
        for milestone in port.list_milestones(plan.id):
            target = _child_rollup(port, "milestone", milestone.id)
            if target is None or target == milestone.status:
                continue
            changes.append({"kind": "milestone", "id": milestone.id, "to": target.value})
            if write:
                heal(port, "milestone", milestone.id, actor)
        target = _child_rollup(port, "plan", plan.id)
        if target is not None and target != plan.status:
            changes.append({"kind": "plan", "id": plan.id, "to": target.value})
            if write:
                heal(port, "plan", plan.id, actor)

    released: list[int] = []
    expired: list[int] = []
    now = time.time()
    for claim in port.list_claims(include_expired=True, now=now):
        task_id = int(claim["task_id"])
        task = port.get_task(task_id)
        if task is None:
            continue
        if claim["expired"]:
            expired.append(task_id)
        elif task.status != Status.DOING:
            released.append(task_id)
        else:
            continue
        if write:
            end_claim(port, task_id, actor)

    ambiguous: list[dict] = []
    for plan in port.list_plans():
        for milestone in port.list_milestones(plan.id):
            for task in port.list_tasks(milestone.id):
                if task.status == Status.DONE and port.open_criteria("task", task.id):
                    ambiguous.append(
                        {"kind": "task", "id": task.id, "reason": "done with open criteria"}
                    )
    return {
        "changes": changes,
        "released": released,
        "expired": expired,
        "ambiguous": ambiguous,
    }


def is_finished(port: PlanningPort, plan: Plan) -> bool:
    """Age-based finished rule: done longer than a day. No proof: never hide."""
    return _is_finished(plan, port.plan_status_events_map(), time.time())


__all__ = [
    "DEFAULT_PLAN_LIMIT",
    "_filtered_milestones",
    "_is_finished",
    "_plan_activity",
    "_plan_matches_repo",
    "_repo_match",
    "_rollup_target",
    "_visible_plan",
    "create_milestone",
    "create_plan",
    "create_task",
    "cycle_status",
    "heal",
    "heal_parents",
    "is_finished",
    "plan_activity",
    "reconcile",
    "set_status",
    "tree",
]
