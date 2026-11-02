"""Pure insight computations: chart rows, timeline spans, and audit windows."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ..entities import Milestone, Status, Task

MilestonesByPlan = dict[int, list[Milestone]]

ETA_WINDOW_DAYS = 14
MILESTONE_LIMIT = 5
ACTIVITY_WEEKS = 12
ACTIVITY_DAYS = ACTIVITY_WEEKS * 7

_ADDED = re.compile(r"^([PMT])#(\d+) ")
_DONE = re.compile(r"^task #(\d+) -> done$")
_TASK_REF = re.compile(r"^(?:T#|task #)(\d+)\b")
_TIMELINE_ADD = re.compile(r"^([PMT])#(\d+) ")
_STATUS_MOVE = re.compile(r"^(plan|milestone|task) #(\d+) -> (todo|doing|done)\b")

_UNITS = {
    "minute": "minutes",
    "minutes": "minutes",
    "hour": "hours",
    "hours": "hours",
    "day": "days",
    "days": "days",
    "week": "weeks",
    "weeks": "weeks",
}


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
class TimelineLane:
    """One project, milestone, or task swimlane on the wall-clock timeline."""

    kind: str
    title: str
    start: float
    end: float
    active: tuple[tuple[float, float], ...] = ()
    selected: bool = False
    trace: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Timeline:
    """Wall-clock spans for the selected row and its immediate children."""

    lanes: tuple[TimelineLane, ...] = ()
    start: float = 0.0
    end: float = 0.0
    now: float = 0.0
    empty: str = ""


@dataclass(frozen=True)
class MetricsSnapshot:
    """Everything the dashboard renders."""

    activity: tuple[DayActivity, ...] = ()
    progress: OverallProgress | None = None
    status: StatusBreakdown | None = None
    timeline: Timeline | None = None
    plan_id: int | None = None
    plan_title: str = ""


def activity_weeks(activity: tuple[DayActivity, ...]) -> tuple[ChartRow, ...]:
    """Sum the daily series into weekly rows."""
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


def add_times(events: list[dict]) -> list[float]:
    """Timestamps of plan, milestone, and task creation events."""
    return [float(event["ts"]) for event in events if _ADDED.match(str(event.get("detail") or ""))]


def latest_task_events(events: list[dict]) -> dict[int, float]:
    """Newest event timestamp for every task id."""
    latest: dict[int, float] = {}
    for event in events:
        found = _TASK_REF.match(str(event.get("detail") or ""))
        if found is not None:
            latest[int(found.group(1))] = float(event["ts"])
    return latest


def done_times(events: list[dict]) -> list[float]:
    """Timestamps of every completion transition."""
    return [float(event["ts"]) for event in events if _DONE.match(str(event.get("detail") or ""))]


def top_milestones(
    milestones_by_plan: MilestonesByPlan,
    tasks_by_milestone: dict[int, list[Task]],
    latest: dict[int, float],
    limit: int = MILESTONE_LIMIT,
) -> tuple[MilestoneProgress, ...]:
    """The busiest milestones, newest activity first."""
    rows: list[tuple[float, MilestoneProgress]] = []
    for milestones in milestones_by_plan.values():
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


def activity(events: list[dict], now: float) -> tuple[DayActivity, ...]:
    """Daily completions for the activity window ending on the local today."""
    today = date.fromtimestamp(now)
    start = today - timedelta(days=ACTIVITY_DAYS - 1)
    counts: dict[date, int] = {}
    for when in done_times(events):
        day = date.fromtimestamp(when)
        if start <= day <= today:
            counts[day] = counts.get(day, 0) + 1
    days: list[DayActivity] = []
    for offset in range(ACTIVITY_DAYS):
        day = start + timedelta(days=offset)
        days.append(DayActivity(day=day, done=counts.get(day, 0)))
    return tuple(days)


def progress(
    milestones_by_plan: MilestonesByPlan,
    tasks_by_milestone: dict[int, list[Task]],
    events: list[dict],
    now: float,
) -> OverallProgress:
    """Completion, elapsed time, and ETA from one task and event snapshot."""
    tasks = [task for items in tasks_by_milestone.values() for task in items]
    done = sum(1 for task in tasks if task.status == Status.DONE)
    starts = add_times(events)
    elapsed = None
    if starts:
        elapsed = max(0.0, now - min(starts))
    recent = [when for when in done_times(events) if now - ETA_WINDOW_DAYS * 86_400 <= when <= now]
    rate = len(recent) / ETA_WINDOW_DAYS
    remaining = len(tasks) - done
    complete = bool(tasks) and remaining == 0
    eta_days = None
    if not complete and remaining > 0 and rate > 0:
        eta_days = math.ceil(remaining / rate)
    eta_date = None
    if eta_days is not None:
        eta_date = date.fromtimestamp(now) + timedelta(days=eta_days)
    return OverallProgress(
        done=done,
        total=len(tasks),
        elapsed_seconds=elapsed,
        daily_rate=rate,
        eta_days=eta_days,
        eta_date=eta_date,
        complete=complete,
        milestones=top_milestones(
            milestones_by_plan, tasks_by_milestone, latest_task_events(events)
        ),
    )


def timeline_starts(events: list[dict]) -> dict[tuple[str, int], float]:
    """Earliest add timestamp for every plan, milestone, and task."""
    starts: dict[tuple[str, int], float] = {}
    for event in events:
        found = _TIMELINE_ADD.match(str(event.get("detail") or ""))
        if found is None:
            continue
        kind = {"P": "plan", "M": "milestone", "T": "task"}[found.group(1)]
        key = (kind, int(found.group(2)))
        stamp = float(event["ts"])
        starts[key] = min(stamp, starts.get(key, stamp))
    return starts


def timeline_ends(events: list[dict]) -> dict[tuple[str, int], float]:
    """Newest completion timestamp for every plan and milestone."""
    ends: dict[tuple[str, int], float] = {}
    for event in events:
        found = _STATUS_MOVE.match(str(event.get("detail") or ""))
        if found is None or found.group(3) != "done":
            continue
        key = (found.group(1), int(found.group(2)))
        stamp = float(event["ts"])
        ends[key] = max(stamp, ends.get(key, stamp))
    return ends


def doing_intervals(
    kind: str,
    oid: int,
    status: Status,
    events: list[dict],
    fallback_start: float,
    now: float,
) -> tuple[tuple[float, float], ...]:
    """Periods when one row's status was doing, with gaps for pauses."""
    intervals: list[tuple[float, float]] = []
    opened: float | None = None
    for event in events:
        found = _STATUS_MOVE.match(str(event.get("detail") or ""))
        if found is None or found.group(1) != kind or int(found.group(2)) != oid:
            continue
        stamp = float(event["ts"])
        target = found.group(3)
        if target == "doing":
            if opened is None:
                opened = stamp
        elif opened is not None:
            intervals.append((opened, max(opened, stamp)))
            opened = None
    if opened is not None:
        intervals.append((opened, max(opened, now)))
    elif status == Status.DOING and not intervals:
        intervals.append((fallback_start, max(fallback_start, now)))
    return tuple(intervals)


def work_span(
    active: tuple[tuple[float, float], ...],
    added: float,
    finished: float | None,
    now: float,
) -> tuple[float, float]:
    """Span from the first doing start to the last doing end, or the add fallback."""
    if active:
        return min(interval[0] for interval in active), max(interval[1] for interval in active)
    return added, max(added, finished if finished is not None else now)


def status_breakdown(tasks: list[Task]) -> StatusBreakdown:
    """Task counts by state and blocked overlay."""
    return StatusBreakdown(
        todo=sum(1 for task in tasks if task.status == Status.TODO),
        doing=sum(1 for task in tasks if task.status == Status.DOING),
        done=sum(1 for task in tasks if task.status == Status.DONE),
        blocked=sum(1 for task in tasks if task.blocked),
    )


def parse_since(text: str) -> float | None:
    """Parse `7.days`, `2.hours`, or an ISO date into an epoch; None stays None."""
    raw = (text or "").strip().lower()
    if not raw:
        return None
    if "." in raw:
        amount, _, unit = raw.partition(".")
        unit_name = _UNITS.get(unit)
        if unit_name is not None:
            try:
                value = float(amount)
            except ValueError:
                return None
            delta = timedelta(**{unit_name: value})
            return (datetime.now(UTC) - delta).timestamp()
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def status_after(
    times: dict[int, list[tuple[float, Status]]], task_id: int, after: int
) -> float | None:
    """Earliest doing/done event at or after one commit."""
    candidates = [
        ts for ts, status in times.get(task_id, []) if ts >= after and status != Status.TODO
    ]
    return min(candidates) if candidates else None
