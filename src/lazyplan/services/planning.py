"""Planning use cases: plans, milestones, tasks, criteria, status, and trees."""

from __future__ import annotations

import time
from pathlib import Path

from lazyplan.infrastructure.templates import apply_template, template_criteria

from ..core.entities import Criterion, Milestone, Plan, Status, Task
from ..core.kinds import check_kind
from ..core.policies.maintenance import check_archive_mode, is_visible
from ..core.policies.planning import is_archived as _is_archived_policy
from ..core.policies.planning import next_status, rollup_target
from ..core.ports.coordination import CoordinationPort
from ..core.ports.planning import PlanningPort

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
    reason: str = "",
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
) -> bool:
    """Move a row, optionally heal the subtree state, and log the transition."""
    check_kind(kind)
    claim = None
    if kind == "task" and status is not Status.DOING:
        get_claim = getattr(port, "get_claim", None)
        if get_claim is not None:
            claim = get_claim(obj_id)
    ok = port.set_status_raw(kind, obj_id, status)
    if ok:
        port.log(actor, kind, "status", f"{kind} #{obj_id} -> {status.value}")
        if claim is not None:
            port.log(actor, "task", "release", f"task #{obj_id} released by status")
        if heal:
            heal_parents(port, kind, obj_id, actor)
    return ok


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
            port.release_claim(task_id, actor, force=True)

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


def is_archived(port: PlanningPort, plan: Plan) -> bool:
    """Age-based finished rule: done longer than a day. No proof: never hide."""
    return _is_finished(plan, port.plan_status_events_map(), time.time())


def _is_finished(plan: Plan, events: dict[int, tuple[float, str]], now: float) -> bool:
    """Age-based finished decision from a preloaded latest-status map."""
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

    def leading_int(text: str, start: int) -> int | None:
        end = start
        while end < len(text) and text[end].isdigit():
            end += 1
        return int(text[start:end]) if end > start else None

    def plan_for_milestone(mid: int | None) -> int | None:
        return milestone_plan.get(mid) if mid is not None else None

    def plan_for_task(tid: int | None) -> int | None:
        if tid is None:
            return None
        return plan_for_milestone(task_milestone.get(tid))

    def plan_for_criterion(cid: int | None) -> int | None:
        if cid is None:
            return None
        found = criterion_parent.get(cid)
        if found is None:
            return None
        kind, parent_id = found
        if kind == "plan":
            return parent_id
        if kind == "milestone":
            return plan_for_milestone(parent_id)
        return plan_for_task(parent_id)

    out: dict[int, float] = {}
    for event in events:
        detail = str(event.get("detail") or "")
        plan_id: int | None = None
        if detail.startswith("P#"):
            plan_id = leading_int(detail, 2)
        elif detail.startswith("plan #"):
            plan_id = leading_int(detail, 6)
        elif detail.startswith("M#"):
            plan_id = plan_for_milestone(leading_int(detail, 2))
        elif detail.startswith("milestone #"):
            plan_id = plan_for_milestone(leading_int(detail, 11))
        elif detail.startswith("T#"):
            plan_id = plan_for_task(leading_int(detail, 2))
        elif detail.startswith("task #"):
            plan_id = plan_for_task(leading_int(detail, 6))
        elif detail.startswith("criteria #"):
            plan_id = plan_for_criterion(leading_int(detail, 10))
        elif detail.startswith("criterion #"):
            plan_id = plan_for_criterion(leading_int(detail, 11))
        if plan_id is None:
            continue
        stamp = float(event.get("ts") or 0.0)
        if stamp > out.get(plan_id, 0.0):
            out[plan_id] = stamp
    return out


def plan_activity(port: PlanningPort) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    return port.plan_activity_map()


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
    finished: str,
    past_finished_window: bool,
    archived: str,
) -> bool:
    """Whether a plan survives status, finished, and archive filters."""
    if not is_visible(plan, archived):
        return False
    if finished == "only" and not past_finished_window:
        return False
    if finished == "hide" and past_finished_window:
        return False
    if status is not None and plan.status != status and not milestones:
        return False
    return True


def _keep_plan(
    plan: Plan,
    plan_id: int | None,
    plan_mode: str,
    repo: str | None,
    milestones: dict[int, list[Milestone]],
    tasks: dict[int, list[Task]],
    repos: dict[tuple[str, int], list[dict]],
) -> bool:
    """Whether one plan survives mode, id, and repo filters."""
    if plan_id is not None and plan.id != plan_id:
        return False
    if plan_mode == "active" and plan.status is Status.DONE:
        return False
    if plan_mode == "finished" and plan.status is not Status.DONE:
        return False
    if repo and not _plan_matches_repo(plan.id, milestones, tasks, repos, repo):
        return False
    return True


def tree(
    port: PlanningPort,
    status: Status | None = None,
    plan_id: int | None = None,
    finished: str = "hide",
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
    plan_mode: str = "all",
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters."""
    check_archive_mode(finished)
    check_archive_mode(archived)
    if plan_mode not in ("all", "active", "finished"):
        raise ValueError("plan_mode must be all|active|finished")
    plans = port.list_plans(archived="show")
    milestones = port.milestones_map()
    tasks = port.tasks_map()
    status_events = port.plan_status_events_map() if finished != "show" else {}
    repos = port.repos_map() if repo else {}
    now = time.time()
    out = []
    for plan in plans:
        if not _keep_plan(plan, plan_id, plan_mode, repo, milestones, tasks, repos):
            continue
        items = _filtered_milestones(milestones, tasks, plan.id, status)
        if milestone_id is not None:
            items = [(item, task_list) for item, task_list in items if item.id == milestone_id]
        if _visible_plan(
            plan,
            items,
            status,
            finished,
            _is_finished(plan, status_events, now),
            archived,
        ):
            out.append((plan, items))
    if plan_id is None and milestone_id is None:
        activity = _plan_activity(
            milestones,
            tasks,
            port.criteria_map(),
            port.feed(limit=100_000),
        )
        out.sort(key=lambda entry: (activity.get(entry[0].id, 0.0), entry[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out


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
    "is_archived",
    "plan_activity",
    "reconcile",
    "set_status",
    "tree",
]
