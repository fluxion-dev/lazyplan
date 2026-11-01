"""Read-only metrics snapshots for the TUI dashboard.

A snapshot is computed from the store and an injected clock. Nothing here
writes, caches, or mutates the database; the dashboard renders one snapshot
at a time.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta

from .models import Status, Task
from .store import Store

_ADDED = re.compile(r"^([PMT])#(\d+) ")
_DONE = re.compile(r"^task #(\d+) -> done$")
_TASK_REF = re.compile(r"^(?:T#|task #)(\d+)\b")
ETA_WINDOW_DAYS = 14
MILESTONE_LIMIT = 5
ACTIVITY_WEEKS = 12
ACTIVITY_DAYS = ACTIVITY_WEEKS * 7


@dataclass(frozen=True)
class DayActivity:
    """Task completions recorded on one local calendar day."""

    day: date
    done: int = 0


@dataclass(frozen=True)
class MilestoneProgress:
    """Done and total task counts for one milestone."""

    milestone_id: int
    plan_id: int
    title: str
    done: int
    total: int

    @property
    def percent(self) -> int:
        """Whole-percent completion, or 0 when the milestone has no tasks."""
        if self.total <= 0:
            return 0
        return round(self.done * 100 / self.total)


@dataclass(frozen=True)
class OverallProgress:
    """Global completion, elapsed time, and the current ETA."""

    done: int = 0
    total: int = 0
    elapsed_seconds: float | None = None
    daily_rate: float = 0.0
    eta_days: int | None = None
    eta_date: date | None = None
    complete: bool = False
    milestones: tuple[MilestoneProgress, ...] = ()

    @property
    def percent(self) -> int:
        """Whole-percent completion, or 0 when there is no work."""
        if self.total <= 0:
            return 0
        return round(self.done * 100 / self.total)


@dataclass(frozen=True)
class StatusBreakdown:
    """Task counts by lifecycle state plus the blocked overlay."""

    todo: int = 0
    doing: int = 0
    done: int = 0
    blocked: int = 0

    @property
    def total(self) -> int:
        """Every task, counted once by its lifecycle state."""
        return self.todo + self.doing + self.done

    def share(self, count: int) -> int:
        """Whole-percent share of all tasks, or 0 when there are none."""
        if self.total <= 0:
            return 0
        return round(count * 100 / self.total)


@dataclass(frozen=True)
class ChartRow:
    """One labelled value ready for a dashboard chart."""

    label: str
    value: int


@dataclass(frozen=True)
class MetricsSnapshot:
    """Everything the three dashboard cards render."""

    activity: tuple[DayActivity, ...] = ()
    progress: OverallProgress | None = None
    status: StatusBreakdown | None = None
    plan_id: int | None = None
    plan_title: str = ""


def activity_weeks(activity: tuple[DayActivity, ...]) -> tuple[ChartRow, ...]:
    """Sum the daily series into 12 weekly rows."""
    rows: list[ChartRow] = []
    for offset in range(0, len(activity), 7):
        week = activity[offset : offset + 7]
        if not week:
            continue
        rows.append(ChartRow(week[0].day.strftime("%m-%d"), sum(day.done for day in week)))
    return tuple(rows)


def milestone_bars(progress: OverallProgress) -> tuple[ChartRow, ...]:
    """One percentage row per ranked milestone."""
    return tuple(ChartRow(item.title, item.percent) for item in progress.milestones)


def status_bars(status: StatusBreakdown) -> tuple[ChartRow, ...]:
    """One row per lifecycle state plus the blocked overlay."""
    rows = (
        ("todo", status.todo),
        ("doing", status.doing),
        ("done", status.done),
        ("blocked", status.blocked),
    )
    return tuple(ChartRow(f"{label} {status.share(count)}%", count) for label, count in rows)


def _events(store: Store) -> list[dict]:
    """Every event, oldest first."""
    return list(reversed(store.feed(limit=1_000_000)))


def _flatten(tasks_by_milestone: dict[int, list[Task]]) -> list[Task]:
    """Every task in one snapshot, in creation order."""
    return [task for tasks in tasks_by_milestone.values() for task in tasks]


def _scoped_tasks(
    store: Store,
    tasks_by_milestone: dict[int, list[Task]],
    plan_id: int | None,
) -> dict[int, list[Task]]:
    """Task map limited to one plan's milestones, or all plans for None."""
    if plan_id is None:
        return tasks_by_milestone
    return {
        milestone.id: tasks_by_milestone.get(milestone.id, [])
        for milestone in store.milestones_map().get(plan_id, ())
    }


def _plan_title(store: Store, plan_id: int | None) -> str:
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
    task_ref = _TASK_REF.match(detail)
    if task_ref is not None:
        return int(task_ref.group(1)) in task_ids
    return False


def _scope_events(
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


def _add_times(events: list[dict]) -> list[float]:
    """Timestamps of plan, milestone, and task creation events."""
    return [float(event["ts"]) for event in events if _ADDED.match(str(event.get("detail") or ""))]


def _latest_task_events(events: list[dict]) -> dict[int, float]:
    """Newest event timestamp for every task id."""
    latest: dict[int, float] = {}
    for event in events:
        found = _TASK_REF.match(str(event.get("detail") or ""))
        if found is not None:
            latest[int(found.group(1))] = float(event["ts"])
    return latest


def _done_times(events: list[dict]) -> list[float]:
    """Timestamps of every completion transition."""
    return [float(event["ts"]) for event in events if _DONE.match(str(event.get("detail") or ""))]


def _top_milestones(
    store: Store,
    tasks_by_milestone: dict[int, list[Task]],
    latest: dict[int, float],
    limit: int = MILESTONE_LIMIT,
) -> tuple[MilestoneProgress, ...]:
    """The busiest milestones, newest activity first."""
    rows: list[tuple[float, MilestoneProgress]] = []
    for milestones in store.milestones_map().values():
        for milestone in milestones:
            tasks = tasks_by_milestone.get(milestone.id, [])
            if not tasks:
                continue
            done = sum(1 for task in tasks if task.status == Status.DONE)
            newest = max((latest.get(task.id, 0.0) for task in tasks), default=0.0)
            rows.append(
                (
                    newest,
                    MilestoneProgress(
                        milestone_id=milestone.id,
                        plan_id=milestone.plan_id,
                        title=milestone.title,
                        done=done,
                        total=len(tasks),
                    ),
                )
            )
    rows.sort(
        key=lambda item: (
            -item[0],
            -(item[1].total - item[1].done),
            item[1].milestone_id,
        )
    )
    return tuple(row for _newest, row in rows[:limit])


def _activity(events: list[dict], now: float) -> tuple[DayActivity, ...]:
    """Daily completions for the 12 weeks ending on the local today."""
    today = date.fromtimestamp(now)
    start = today - timedelta(days=ACTIVITY_DAYS - 1)
    counts: dict[date, int] = {}
    for when in _done_times(events):
        day = date.fromtimestamp(when)
        if start <= day <= today:
            counts[day] = counts.get(day, 0) + 1
    days: list[DayActivity] = []
    for offset in range(ACTIVITY_DAYS):
        day = start + timedelta(days=offset)
        days.append(DayActivity(day=day, done=counts.get(day, 0)))
    return tuple(days)


def _progress(
    store: Store,
    tasks_by_milestone: dict[int, list[Task]],
    events: list[dict],
    now: float | None,
) -> OverallProgress:
    """Completion, elapsed time, and ETA from one task and event snapshot."""
    tasks = _flatten(tasks_by_milestone)
    done = sum(1 for task in tasks if task.status == Status.DONE)
    starts = _add_times(events)
    stamp = time.time() if now is None else now
    elapsed = None
    if starts:
        elapsed = max(0.0, stamp - min(starts))
    recent = [
        when for when in _done_times(events) if stamp - ETA_WINDOW_DAYS * 86_400 <= when <= stamp
    ]
    rate = len(recent) / ETA_WINDOW_DAYS
    remaining = len(tasks) - done
    complete = bool(tasks) and remaining == 0
    eta_days = None
    if not complete and remaining > 0 and rate > 0:
        eta_days = math.ceil(remaining / rate)
    eta_date = None
    if eta_days is not None:
        eta_date = date.fromtimestamp(stamp) + timedelta(days=eta_days)
    return OverallProgress(
        done=done,
        total=len(tasks),
        elapsed_seconds=elapsed,
        daily_rate=rate,
        eta_days=eta_days,
        eta_date=eta_date,
        complete=complete,
        milestones=_top_milestones(store, tasks_by_milestone, _latest_task_events(events)),
    )


def _status(tasks: list[Task]) -> StatusBreakdown:
    return StatusBreakdown(
        todo=sum(1 for task in tasks if task.status == Status.TODO),
        doing=sum(1 for task in tasks if task.status == Status.DOING),
        done=sum(1 for task in tasks if task.status == Status.DONE),
        blocked=sum(1 for task in tasks if task.blocked),
    )


def snapshot(
    store: Store,
    now: float | None = None,
    plan_id: int | None = None,
) -> MetricsSnapshot:
    """Build the dashboard snapshot from one task and event read.

    plan_id limits task counts, status shares, milestone bars, activity,
    elapsed time, and the ETA to that plan. None keeps the all-plans view.
    """
    tasks_by_milestone = _scoped_tasks(store, store.tasks_map(), plan_id)
    events = _scope_events(_events(store), plan_id, tasks_by_milestone)
    stamp = time.time() if now is None else now
    title = _plan_title(store, plan_id)
    return MetricsSnapshot(
        activity=_activity(events, stamp),
        progress=_progress(store, tasks_by_milestone, events, stamp),
        status=_status(_flatten(tasks_by_milestone)),
        plan_id=plan_id if title else None,
        plan_title=title,
    )
