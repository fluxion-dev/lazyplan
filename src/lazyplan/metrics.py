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
class MetricsSnapshot:
    """Everything the three dashboard cards render."""

    activity: tuple[DayActivity, ...] = ()
    progress: OverallProgress | None = None
    status: StatusBreakdown | None = None


def _events(store: Store) -> list[dict]:
    """Every event, oldest first."""
    return list(reversed(store.feed(limit=1_000_000)))


def _flatten(tasks_by_milestone: dict[int, list[Task]]) -> list[Task]:
    """Every task in one snapshot, in creation order."""
    return [task for tasks in tasks_by_milestone.values() for task in tasks]


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


def snapshot(store: Store, now: float | None = None) -> MetricsSnapshot:
    """Build the dashboard snapshot from one task and event read."""
    tasks_by_milestone = store.tasks_map()
    events = _events(store)
    return MetricsSnapshot(
        progress=_progress(store, tasks_by_milestone, events, now),
        status=_status(_flatten(tasks_by_milestone)),
    )
