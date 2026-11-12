"""Read-only metrics snapshots for the TUI dashboard.

A snapshot is computed from the store and an injected clock. Nothing here
writes, caches, or mutates the database; the dashboard renders one snapshot
at a time.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from ..core.entities import Milestone, Plan, Status, Task
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


@dataclass
class _LaneBuilder:
    """Build timeline lanes for one snapshot's event map and scope."""

    events: list[dict]
    starts: dict[tuple[str, int], float]
    ends: dict[tuple[str, int], float]
    fallback: float
    scope_kind: str | None
    scope_id: int | None
    now: float

    def lane(self, kind: str, oid: int, title: str, status: Status) -> TimelineLane:
        """One lane with its doing intervals and selected flag."""
        selected = self.scope_kind == kind and self.scope_id == oid
        added = self.starts.get((kind, oid), self.fallback)
        active = _doing_intervals(kind, oid, status, self.events, added, self.now)
        start, lane_end = _work_span(active, added, self.ends.get((kind, oid)), self.now)
        return TimelineLane(kind, title, start, lane_end, active, selected, active)

    def task(self, task: Task) -> TimelineLane:
        """One task lane."""
        return self.lane("task", task.id, task.title, task.status)

    def milestone(self, milestone: Milestone) -> TimelineLane:
        """One milestone lane."""
        return self.lane("milestone", milestone.id, milestone.title, milestone.status)

    def milestone_start(self, milestone: Milestone) -> float:
        """Sort key for milestone lanes."""
        return self.starts.get(("milestone", milestone.id), self.fallback)


def _scoped_task(
    tasks_by_id: dict[int, Task], scope_kind: str | None, scope_id: int | None
) -> Task | None:
    """The clicked task, when the selection is a task."""
    if scope_kind != "task" or scope_id is None:
        return None
    return tasks_by_id.get(scope_id)


def _scoped_milestone(
    milestones_by_id: dict[int, Milestone], scope_kind: str | None, scope_id: int | None
) -> Milestone | None:
    """The clicked milestone, when the selection is a milestone."""
    if scope_kind != "milestone" or scope_id is None:
        return None
    return milestones_by_id.get(scope_id)


def _selected_plan_id(
    plan_id: int | None, scope_kind: str | None, scope_id: int | None
) -> int | None:
    """The clicked plan, falling back to the snapshot's plan scope."""
    if scope_kind == "plan" and scope_id is not None:
        return scope_id
    return plan_id


def _empty_reason(plans: list[Plan], selected_plan: int | None) -> str:
    """Empty copy for a missing plan or a snapshot with no selection."""
    if not plans or selected_plan is not None:
        return "no plans yet"
    return "select a row"


def _pack(lanes: list[TimelineLane], now: float) -> Timeline:
    """Assemble a timeline window from its visible lanes."""
    return Timeline(
        lanes=tuple(lanes),
        start=min(lane.start for lane in lanes),
        end=max(lane.end for lane in lanes),
        now=now,
    )


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
    """Wall-clock spans for the selected row and its immediate children.

    The clicked row decides the lane set: a plan keeps its own lane plus its
    milestones, a milestone keeps its own lane plus its tasks, and a task
    keeps only its own lane. With no selection the card renders the empty
    state. A lane starts at its add event and ends at its latest completion
    event when the row is done; open work runs to `now`. The lane that
    matches `scope_kind`/`scope_id` is marked selected; ancestors and
    siblings are never added.
    """
    starts = _timeline_starts(events)
    ends = _timeline_ends(events)
    fallback = min((float(event["ts"]) for event in events), default=now)
    builder = _LaneBuilder(events, starts, ends, fallback, scope_kind, scope_id, now)
    tasks_by_id = {
        task.id: task for milestone_tasks in tasks_by_milestone.values() for task in milestone_tasks
    }
    task = _scoped_task(tasks_by_id, scope_kind, scope_id)
    if task is not None:
        return _pack([builder.task(task)], now)
    milestones_by_id = {
        milestone.id: milestone
        for plan_milestones in milestones_by_plan.values()
        for milestone in plan_milestones
    }
    milestone = _scoped_milestone(milestones_by_id, scope_kind, scope_id)
    if milestone is not None:
        lanes = [builder.milestone(milestone)]
        lanes.extend(builder.task(item) for item in tasks_by_milestone.get(milestone.id, []))
        return _pack(lanes, now)
    selected_plan = _selected_plan_id(plan_id, scope_kind, scope_id)
    plan = next((item for item in plans if item.id == selected_plan), None)
    if plan is None:
        return Timeline(empty=_empty_reason(plans, selected_plan), now=now)
    lanes = [builder.lane("plan", plan.id, plan.name, plan.status)]
    lanes.extend(
        builder.milestone(item)
        for item in sorted(milestones_by_plan.get(plan.id, []), key=builder.milestone_start)
    )
    return _pack(lanes, now)


def snapshot(
    store: InsightsPort,
    now: float | None = None,
    plan_id: int | None = None,
    scope_kind: str | None = None,
    scope_id: int | None = None,
) -> MetricsSnapshot:
    """Build the dashboard snapshot from one task and event read.

    plan_id limits task counts, status shares, milestone bars, activity,
    elapsed time, and the ETA to that plan. scope_kind/scope_id select the
    timeline lanes: a plan keeps its milestones, a milestone keeps its tasks,
    and a task keeps only itself. None keeps the empty state.
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
            store.list_plans(archived="show" if plan_id is not None else "hide"),
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
