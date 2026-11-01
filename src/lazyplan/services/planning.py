"""Planning use cases: plans, milestones, tasks, criteria, status, and trees."""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..core.entities import Criterion, Milestone, Plan, Status, Task
from ..core.policies.planning import is_archived as _is_archived_policy
from ..core.policies.planning import next_status, rollup_target
from ..core.ports.planning import PlanningPort
from ..kinds import check_kind
from ..templates import apply_template, template_criteria

DEFAULT_PLAN_LIMIT = 5

#: Backward-compatible private alias used by the services facade.
_rollup_target = rollup_target


def create_plan(
    port: PlanningPort,
    name: str,
    description: str = "",
    goal: str = "",
    actor: str = "human",
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
    )
    for text in template_criteria("milestone", port.db_path):
        port.add_criteria("milestone", milestone.id, text, actor=actor)
    return milestone


def create_task(
    port: PlanningPort,
    milestone_id: int,
    title: str,
    description: str = "",
    actor: str = "human",
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
    )
    for text in template_criteria("task", port.db_path):
        port.add_criteria("task", task.id, text, actor=actor)
    return task


def heal(port: PlanningPort, kind: str, obj_id: int, actor: str = "human") -> bool:
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
    if obj is None or not kids:
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


def set_status(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    status: Status,
    actor: str = "human",
) -> bool:
    """Move a row, heal the subtree state, and log the transition."""
    check_kind(kind)
    ok = port.set_status_raw(kind, obj_id, status)
    if ok:
        port.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        heal_parents(port, kind, obj_id, actor)
    return ok


def cycle_status(
    port: PlanningPort,
    kind: str,
    obj_id: int,
    actor: str = "human",
) -> Status | None:
    """Advance todo to doing to done to todo."""
    check_kind(kind)
    obj = port.get_parent(kind, obj_id)
    if obj is None:
        return None
    status = next_status(obj.status)
    set_status(port, kind, obj_id, status, actor=actor)
    return status


def reconcile(port: PlanningPort, actor: str = "human") -> list[dict]:
    """Recompute every parent from its children; childless rows untouched."""
    changes: list[dict] = []
    for plan in port.list_plans():
        before_plan = plan.status
        for milestone in port.list_milestones(plan.id):
            before = milestone.status
            heal(port, "milestone", milestone.id, actor)
            after = port.get_milestone(milestone.id)
            if after is not None and after.status != before:
                changes.append({"kind": "milestone", "id": milestone.id, "to": after.status.value})
        heal(port, "plan", plan.id, actor)
        after_plan = port.get_plan(plan.id)
        if after_plan is not None and after_plan.status != before_plan:
            changes.append({"kind": "plan", "id": plan.id, "to": after_plan.status.value})
    return changes


def is_archived(port: PlanningPort, plan: Plan) -> bool:
    """Done longer than a day, with history to prove it. No proof: never hide."""
    return _is_archived(plan, port.plan_status_events_map(), time.time())


def _is_archived(plan: Plan, events: dict[int, tuple[float, str]], now: float) -> bool:
    """Archive decision from a preloaded latest-status map."""
    return _is_archived_policy(plan, events, now)


def _plan_activity(
    milestones: dict[int, list[Milestone]],
    tasks: dict[int, list[Task]],
    criteria: dict[tuple[str, int], list[Criterion]],
    events: list[dict],
) -> dict[int, float]:
    """Latest event timestamp per plan from preloaded maps and events."""
    milestone_plan: dict[int, int] = {
        milestone.id: milestone.plan_id for items in milestones.values() for milestone in items
    }
    task_milestone: dict[int, int] = {
        task.id: task.milestone_id for items in tasks.values() for task in items
    }
    criterion_parent: dict[int, tuple[str, int]] = {
        criterion.id: (criterion.parent_kind, criterion.parent_id)
        for items in criteria.values()
        for criterion in items
    }

    def resolve(kind: str, detail: str) -> int | None:
        match = re.match(r"([PMT])#(\d+)", detail)
        if match:
            letter, oid = match.group(1), int(match.group(2))
            if letter == "P":
                return oid
            if letter == "M":
                return milestone_plan.get(oid)
            chained = task_milestone.get(oid)
            return milestone_plan.get(chained) if chained is not None else None
        match = re.match(r"(plan|milestone|task) #(\d+)", detail)
        if match:
            kind, oid = match.group(1), int(match.group(2))
            if kind == "plan":
                return oid
            if kind == "milestone":
                return milestone_plan.get(oid)
            chained = task_milestone.get(oid)
            return milestone_plan.get(chained) if chained is not None else None
        match = re.match(r"criteria #(\d+)", detail)
        if match:
            found = criterion_parent.get(int(match.group(1)))
            if found is None:
                return None
            criterion_kind, parent_id = found
            if criterion_kind == "plan":
                return parent_id
            if criterion_kind == "milestone":
                return milestone_plan.get(parent_id)
            chained = task_milestone.get(parent_id)
            return milestone_plan.get(chained) if chained is not None else None
        return None

    out: dict[int, float] = {}
    for event in events:
        plan_id = resolve(str(event["kind"]), str(event["detail"] or ""))
        if plan_id is not None and event["ts"] > out.get(plan_id, 0.0):
            out[plan_id] = event["ts"]
    return out


def plan_activity(port: PlanningPort) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    return _plan_activity(
        port.milestones_map(),
        port.tasks_map(),
        port.criteria_map(),
        port.feed(limit=1_000_000),
    )


def _filtered_milestones(
    milestones: dict[int, list[Milestone]],
    tasks: dict[int, list[Task]],
    plan_id: int,
    status: Status | None,
) -> list[tuple[Milestone, list[Task]]]:
    """Milestone/task pairs of one plan honoring the status filter."""
    out = []
    for milestone in milestones.get(plan_id, ()):
        items = tasks.get(milestone.id, [])
        if status is not None:
            items = [task for task in items if task.status == status]
            if milestone.status != status and not items:
                continue
        out.append((milestone, items))
    return out


def _repo_match(want: str, repos: list[dict]) -> bool:
    """True when a repo filter matches any effective repo (path or remote)."""
    needle = (want or "").strip()
    if not needle:
        return True
    try:
        norm = str(Path(needle).expanduser().resolve())
    except OSError:
        norm = str(Path(needle).expanduser().absolute())
    lowered = needle.lower()
    for repo in repos:
        path = str(repo.get("repo_path", "") or "")
        remote = str(repo.get("repo_remote", "") or "")
        if path and (path == norm or path == needle):
            return True
        if remote and (remote == needle or lowered in remote.lower()):
            return True
        if needle in path:
            return True
    return False


def _plan_matches_repo(
    plan_id: int,
    milestones: dict[int, list[Milestone]],
    tasks: dict[int, list[Task]],
    repos: dict[tuple[str, int], list[dict]],
    want: str,
) -> bool:
    """True when a plan or any descendant effectively links the wanted repo."""
    plan_repos = repos.get(("plan", plan_id), [])
    if _repo_match(want, plan_repos):
        return True
    for milestone in milestones.get(plan_id, ()):
        milestone_repos = repos.get(("milestone", milestone.id), []) or plan_repos
        if _repo_match(want, milestone_repos):
            return True
        for task in tasks.get(milestone.id, ()):
            task_repos = repos.get(("task", task.id), []) or milestone_repos
            if _repo_match(want, task_repos):
                return True
    return False


def _visible_plan(
    plan: Plan,
    milestones: list[tuple[Milestone, list[Task]]],
    status: Status | None,
    archived: str,
    archived_now: bool,
) -> bool:
    """Whether a plan survives status and archive filters."""
    if archived == "only" and not archived_now:
        return False
    if archived == "hide" and archived_now:
        return False
    if status is not None and plan.status != status and not milestones:
        return False
    return True


def tree(
    port: PlanningPort,
    status: Status | None = None,
    plan_id: int | None = None,
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters."""
    if archived not in ("hide", "only", "show"):
        raise ValueError("archived must be hide|only|show")
    plans = port.list_plans()
    milestones = port.milestones_map()
    tasks = port.tasks_map()
    status_events = port.plan_status_events_map() if archived != "show" else {}
    repos = port.repos_map() if repo else {}
    now = time.time()
    out = []
    for plan in plans:
        if plan_id is not None and plan.id != plan_id:
            continue
        if repo and not _plan_matches_repo(plan.id, milestones, tasks, repos, repo):
            continue
        items = _filtered_milestones(milestones, tasks, plan.id, status)
        if milestone_id is not None:
            items = [(item, task_list) for item, task_list in items if item.id == milestone_id]
        if _visible_plan(
            plan,
            items,
            status,
            archived,
            _is_archived(plan, status_events, now),
        ):
            out.append((plan, items))
    if plan_id is None and milestone_id is None:
        activity = _plan_activity(
            milestones,
            tasks,
            port.criteria_map(),
            port.feed(limit=1_000_000),
        )
        out.sort(key=lambda entry: (activity.get(entry[0].id, 0.0), entry[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out


__all__ = [
    "DEFAULT_PLAN_LIMIT",
    "_filtered_milestones",
    "_is_archived",
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
    "is_archived",
    "plan_activity",
    "reconcile",
    "set_status",
    "tree",
]
