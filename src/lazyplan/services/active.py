"""One selection and traversal path for the plans a request works on.

``brief``, ``context``, ``needs_me``, and ``stats`` each answer the same two
questions: which plan (or plans) the request is about, and which tasks sit
under it. Answering them here keeps a change to the rule from having to be made
once per surface.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..core.entities import Plan, Status, Task
from ..core.policies.maintenance import is_archived_row
from ..core.ports.insights import InsightsPort

#: Doing plans a summary may carry before it falls back to one todo plan.
DEFAULT_PLAN_LIMIT = 3


def live_plans(port: InsightsPort) -> list[Plan]:
    """Every unarchived plan, newest first."""
    return port.list_plans(archived="hide")


def requested_plan(port: InsightsPort, plan_id: int) -> Plan | None:
    """One plan by id, or None when it is missing or archived."""
    plan = port.get_plan(plan_id)
    if plan is None or is_archived_row(plan):
        return None
    return plan


def plan_list(port: InsightsPort, plan_id: int | None = None) -> list[Plan]:
    """The one requested plan, or every live plan when none is named."""
    if plan_id is None:
        return live_plans(port)
    plan = requested_plan(port, plan_id)
    return [] if plan is None else [plan]


def next_plans(port: InsightsPort, limit: int = DEFAULT_PLAN_LIMIT) -> list[Plan]:
    """Doing plans first, up to *limit*; otherwise the newest todo plan."""
    plans = live_plans(port)
    doing = [plan for plan in plans if plan.status == Status.DOING]
    if doing:
        return doing[:limit]
    todo = [plan for plan in plans if plan.status == Status.TODO]
    return todo[:1]


def active_plans(
    port: InsightsPort,
    plan_id: int | None = None,
    limit: int = DEFAULT_PLAN_LIMIT,
) -> list[Plan]:
    """The requested plan, or the plans a summary should describe."""
    if plan_id is not None:
        return plan_list(port, plan_id)
    return next_plans(port, limit)


def selected_plan(port: InsightsPort, plan_id: int | None = None) -> Plan | None:
    """The one plan a single-plan surface works on."""
    plans = active_plans(port, plan_id, limit=1)
    return plans[0] if plans else None


def tasks_for(port: InsightsPort, plan: Plan) -> list[Task]:
    """Every task under *plan*, in milestone then creation order."""
    return [
        task
        for milestone in port.list_milestones(plan.id)
        for task in port.list_tasks(milestone.id)
    ]


def task_index(
    port: InsightsPort,
    plan_ids: Iterable[int],
) -> tuple[dict[int, int], dict[int, Task], dict[int, list[Task]]]:
    """Task to plan, task by id, and per-plan lists, from two bulk reads."""
    milestones = port.milestones_map()
    tasks = port.tasks_map()
    task_plan: dict[int, int] = {}
    task_by_id: dict[int, Task] = {}
    tasks_by_plan: dict[int, list[Task]] = {}
    for plan_id in plan_ids:
        plan_tasks = tasks_by_plan.setdefault(plan_id, [])
        for milestone in milestones.get(plan_id, ()):
            for task in tasks.get(milestone.id, ()):
                task_plan[task.id] = plan_id
                task_by_id[task.id] = task
                plan_tasks.append(task)
    return task_plan, task_by_id, tasks_by_plan


def all_tasks(port: InsightsPort) -> list[Task]:
    """Every task under a live plan, in plan then creation order."""
    plans = live_plans(port)
    _, _, tasks_by_plan = task_index(port, (plan.id for plan in plans))
    return [task for plan in plans for task in tasks_by_plan.get(plan.id, ())]
