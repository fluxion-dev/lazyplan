"""Read-only metrics snapshots for the TUI dashboard.

A snapshot is computed from the store and an injected clock. Nothing here
writes, caches, or mutates the database; the dashboard renders one snapshot
at a time.
"""

from __future__ import annotations

import re
import time

from ..core.entities import Plan, Status, Task
from ..core.policies.insights import ACTIVITY_DAYS as ACTIVITY_DAYS
from ..core.policies.insights import ACTIVITY_WEEKS as ACTIVITY_WEEKS
from ..core.policies.insights import ETA_WINDOW_DAYS as ETA_WINDOW_DAYS
from ..core.policies.insights import MILESTONE_LIMIT as MILESTONE_LIMIT
from ..core.policies.insights import ChartRow as ChartRow
from ..core.policies.insights import DayActivity as DayActivity
from ..core.policies.insights import (
    MetricsSnapshot,
    MilestonesByPlan,
    Timeline,
    TimelineLane,
)
from ..core.policies.insights import MilestoneProgress as MilestoneProgress
from ..core.policies.insights import OverallProgress as OverallProgress
from ..core.policies.insights import StatusBreakdown as StatusBreakdown
from ..core.policies.insights import (
    activity as _activity,
)
from ..core.policies.insights import activity_weeks as activity_weeks
from ..core.policies.insights import (
    doing_intervals as _doing_intervals,
)
from ..core.policies.insights import milestone_bars as milestone_bars
from ..core.policies.insights import (
    progress as _progress,
)
from ..core.policies.insights import status_bars as status_bars
from ..core.policies.insights import (
    status_breakdown as _status,
)
from ..core.policies.insights import (
    timeline_ends as _timeline_ends,
)
from ..core.policies.insights import (
    timeline_starts as _timeline_starts,
)
from ..core.policies.insights import (
    work_span as _work_span,
)
from ..core.ports.insights import InsightsPort

_ADDED = re.compile(r"^([PMT])#(\d+) ")
_TASK_REF = re.compile(r"^(?:T#|task #)(\d+)\b")
_STATUS_MOVE = re.compile(r"^(plan|milestone|task) #(\d+) -> (todo|doing|done)\b")


def _events(store: InsightsPort) -> list[dict]:
    """Every event, oldest first."""
    return list(reversed(store.feed(limit=1_000_000)))


def _flatten(tasks_by_milestone: dict[int, list[Task]]) -> list[Task]:
    """Every task in one snapshot, in creation order."""
    return [task for tasks in tasks_by_milestone.values() for task in tasks]


def _scoped_tasks(
    milestones_by_plan: MilestonesByPlan,
    tasks_by_milestone: dict[int, list[Task]],
    plan_id: int | None,
) -> dict[int, list[Task]]:
    """Task map limited to one plan's milestones, or all plans for None."""
    if plan_id is None:
        return tasks_by_milestone
    return {
        milestone.id: tasks_by_milestone.get(milestone.id, [])
        for milestone in milestones_by_plan.get(plan_id, ())
    }


def _plan_title(store: InsightsPort, plan_id: int | None) -> str:
    """The scoped plan's title, or an empty string for the global view."""
    if plan_id is None:
        return ""
    plan = store.get_plan(plan_id)
    return plan.name if plan is not None else ""


def _event_in_scope(
    detail: str,
    plan_id: int,
    milestone_ids: set[int],
    task_ids: set[int],
) -> bool:
    """Whether one event detail names the scoped plan or its descendants."""
    added = _ADDED.match(detail)
    if added is not None:
        letter, oid = added.group(1), int(added.group(2))
        if letter == "P":
            return oid == plan_id
        if letter == "M":
            return oid in milestone_ids
        return oid in task_ids
    finished = _STATUS_MOVE.match(detail)
    if finished is not None:
        kind, oid = finished.group(1), int(finished.group(2))
        if kind == "plan":
            return oid == plan_id
        if kind == "milestone":
            return oid in milestone_ids
        return oid in task_ids
    task_ref = _TASK_REF.match(detail)
    if task_ref is not None:
        return int(task_ref.group(1)) in task_ids
    return False


def _scoped_events(
    events: list[dict],
    plan_id: int | None,
    tasks_by_milestone: dict[int, list[Task]],
) -> list[dict]:
    """Events that belong to the scoped plan, or every event for None."""
    if plan_id is None:
        return events
    milestone_ids = set(tasks_by_milestone)
    task_ids = {task.id for task in _flatten(tasks_by_milestone)}
    return [
        event
        for event in events
        if _event_in_scope(str(event.get("detail") or ""), plan_id, milestone_ids, task_ids)
    ]


def _focused_milestone(
    tasks_by_milestone: dict[int, list[Task]], scope_kind: str | None, scope_id: int | None
) -> int | None:
    """Milestone whose tasks should appear for the current selection."""
    if scope_kind == "milestone":
        return scope_id
    if scope_kind != "task" or scope_id is None:
        return None
    for milestone_id, tasks in tasks_by_milestone.items():
        if any(task.id == scope_id for task in tasks):
            return milestone_id
    return None


def _timeline(
    plans: list[Plan],
    milestones_by_plan: MilestonesByPlan,
    tasks_by_milestone: dict[int, list[Task]],
    events: list[dict],
    plan_id: int | None,
    scope_kind: str | None,
    scope_id: int | None,
    now: float,
) -> Timeline:
    """Wall-clock spans for one plan, its milestones, and focused tasks.

    A lane starts at its add event and ends at its latest completion event
    when the row is done; open work runs to `now`. With no plan scope every
    plan gets a lane; a scoped plan adds one lane per milestone. A milestone
    or task selection adds the focused milestone's task lanes. The lane that
    matches `scope_kind`/`scope_id` is marked selected; ancestors and siblings
    are not.
    """
    starts = _timeline_starts(events)
    ends = _timeline_ends(events)
    fallback = min((float(event["ts"]) for event in events), default=now)

    def is_selected(kind: str, oid: int) -> bool:
        return scope_kind == kind and scope_id == oid

    def lane(
        kind: str, oid: int, title: str, status: Status, selected: bool = False
    ) -> TimelineLane:
        added = starts.get((kind, oid), fallback)
        active = _doing_intervals(kind, oid, status, events, added, now)
        start, lane_end = _work_span(active, added, ends.get((kind, oid)), now)
        return TimelineLane(kind, title, start, lane_end, active, selected, active)

    lanes: list[TimelineLane] = []
    if plan_id is None:
        ordered = sorted(plans, key=lambda item: starts.get(("plan", item.id), fallback))
        lanes = [
            lane("plan", plan.id, plan.name, plan.status, is_selected("plan", plan.id))
            for plan in ordered
        ]
    else:
        plan = next((item for item in plans if item.id == plan_id), None)
        if plan is None:
            return Timeline(empty="no plans yet", now=now)
        milestones = sorted(
            milestones_by_plan.get(plan_id, []),
            key=lambda item: starts.get(("milestone", item.id), fallback),
        )
        if not milestones:
            return Timeline(empty="no milestones yet", now=now)
        lanes.append(lane("plan", plan.id, plan.name, plan.status, is_selected("plan", plan.id)))
        lanes.extend(
            lane(
                "milestone",
                milestone.id,
                milestone.title,
                milestone.status,
                is_selected("milestone", milestone.id),
            )
            for milestone in milestones
        )
        focused_milestone = _focused_milestone(tasks_by_milestone, scope_kind, scope_id)
        if focused_milestone is not None:
            lanes.extend(
                lane(
                    "task",
                    task.id,
                    task.title,
                    task.status,
                    is_selected("task", task.id),
                )
                for task in tasks_by_milestone.get(focused_milestone, [])
            )
    if not lanes:
        return Timeline(empty="no plans yet", now=now)
    return Timeline(
        lanes=tuple(lanes),
        start=min(item.start for item in lanes),
        end=max(item.end for item in lanes),
        now=now,
    )


def snapshot(
    store: InsightsPort,
    now: float | None = None,
    plan_id: int | None = None,
    scope_kind: str | None = None,
    scope_id: int | None = None,
) -> MetricsSnapshot:
    """Build the dashboard snapshot from one task and event read.

    plan_id limits task counts, status shares, milestone bars, activity,
    elapsed time, and the ETA to that plan. scope_kind/scope_id mark the
    selected lane and add the focused milestone's task lanes when a milestone
    or task is selected. None keeps the all-plans view.
    """
    milestones_by_plan = store.milestones_map()
    tasks_by_milestone = _scoped_tasks(milestones_by_plan, store.tasks_map(), plan_id)
    events = _scoped_events(_events(store), plan_id, tasks_by_milestone)
    stamp = time.time() if now is None else now
    title = _plan_title(store, plan_id)
    return MetricsSnapshot(
        activity=_activity(events, stamp),
        progress=_progress(milestones_by_plan, tasks_by_milestone, events, stamp),
        status=_status(_flatten(tasks_by_milestone)),
        timeline=_timeline(
            store.list_plans(),
            milestones_by_plan,
            tasks_by_milestone,
            events,
            plan_id,
            scope_kind,
            scope_id,
            stamp,
        ),
        plan_id=plan_id if title else None,
        plan_title=title,
    )
