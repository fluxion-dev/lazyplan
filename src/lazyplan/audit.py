"""Read-only accuracy metrics: commit linkage, status lag, and criteria gaps.

The audit answers one question per plan: did the journal keep up with the
code? It reads existing events, commit links, and git history, and never
writes to the database. Stdlib only.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import vcs
from .models import Status
from .store import Store

_STATUS = re.compile(r"^(plan|milestone|task) #(\d+) -> (todo|doing|done)")
_ADDED = re.compile(r"^([PST])#(\d+) ")
_DEFAULT_COVERAGE = 0.8
_DEFAULT_LAG = 1.0
_DEFAULT_GAPS = 0
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
class Commit:
    """One implementation commit inside the audit window."""

    sha: str
    timestamp: int
    repo: str = ""
    parents: int = 0
    subject: str = ""


@dataclass(frozen=True)
class Gap:
    """An open criterion on a row that is already done."""

    kind: str
    id: int
    text: str


@dataclass
class Report:
    """Audit result for one or more plans."""

    plans: list[int] = field(default_factory=list)
    since: float = 0.0
    repos: list[str] = field(default_factory=list)
    commits_total: int = 0
    commits_linked: int = 0
    lag_commits: list[float] = field(default_factory=list)
    lag_minutes: list[float] = field(default_factory=list)
    unresolved: int = 0
    gaps: list[Gap] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        """Linked commits over total commits; a window with no work scores 1."""
        if self.commits_total == 0:
            return 1.0
        return self.commits_linked / self.commits_total

    @property
    def median_lag_commits(self) -> float:
        return round(statistics.median(self.lag_commits), 2) if self.lag_commits else 0.0

    @property
    def median_lag_minutes(self) -> float:
        return round(statistics.median(self.lag_minutes), 1) if self.lag_minutes else 0.0

    def to_dict(self) -> dict:
        """JSON-safe report for agents and scripts."""
        return {
            "plans": list(self.plans),
            "since": self.since,
            "repos": list(self.repos),
            "commits_total": self.commits_total,
            "commits_linked": self.commits_linked,
            "coverage": round(self.coverage, 4),
            "median_lag_commits": self.median_lag_commits,
            "median_lag_minutes": self.median_lag_minutes,
            "unresolved_lag": self.unresolved,
            "criteria_gaps": [
                {"kind": gap.kind, "id": gap.id, "text": gap.text} for gap in self.gaps
            ],
        }


@dataclass(frozen=True)
class Thresholds:
    """Strict-mode limits; defaults are intentionally achievable."""

    coverage: float = _DEFAULT_COVERAGE
    lag_commits: float = _DEFAULT_LAG
    gaps: int = _DEFAULT_GAPS

    def breaches(self, report: Report) -> list[str]:
        """Human-readable reasons the report fails strict mode."""
        out: list[str] = []
        if report.commits_total and report.coverage < self.coverage:
            out.append(
                f"coverage {report.coverage:.0%} < {self.coverage:.0%} "
                f"({report.commits_linked}/{report.commits_total} commits)"
            )
        if report.lag_commits and report.median_lag_commits > self.lag_commits:
            out.append(f"median lag {report.median_lag_commits:g} commits > {self.lag_commits:g}")
        if len(report.gaps) > self.gaps:
            out.append(f"{len(report.gaps)} open criteria on done rows > {self.gaps}")
        return out


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


def plan_starts(store: Store) -> dict[int, float]:
    """Plan id -> add-event timestamp, in one pass over the feed."""
    out: dict[int, float] = {}
    for event in reversed(store.feed(limit=100000)):
        found = _ADDED.match(str(event.get("detail") or ""))
        if found is None or found.group(1) != "P":
            continue
        out.setdefault(int(found.group(2)), float(event["ts"]))
    return out


def plan_start(store: Store, plan_id: int) -> float | None:
    """Timestamp of the plan add event, or the earliest event naming it."""
    starts = plan_starts(store)
    if plan_id in starts:
        return starts[plan_id]
    earliest: float | None = None
    for event in store.feed(limit=100000):
        found = _ADDED.match(str(event.get("detail") or ""))
        if found is not None and found.group(2) == str(plan_id):
            stamp = float(event["ts"])
            if earliest is None or stamp < earliest:
                earliest = stamp
    return earliest


def _status_times(store: Store) -> dict[int, list[tuple[float, Status]]]:
    """Per-task status events, oldest first."""
    out: dict[int, list[tuple[float, Status]]] = {}
    for event in reversed(store.feed(limit=100000)):
        if event.get("action") != "status":
            continue
        found = _STATUS.match(str(event.get("detail") or ""))
        if found is None or found.group(1) != "task":
            continue
        task_id = int(found.group(2))
        out.setdefault(task_id, []).append((float(event["ts"]), Status(found.group(3))))
    return out


def _done_times(store: Store) -> dict[tuple[str, int], float]:
    """Latest done event per row, oldest-first scan so the last write wins."""
    out: dict[tuple[str, int], float] = {}
    for event in reversed(store.feed(limit=100000)):
        if event.get("action") != "status":
            continue
        found = _STATUS.match(str(event.get("detail") or ""))
        if found is None or found.group(3) != "done":
            continue
        out[(found.group(1), int(found.group(2)))] = float(event["ts"])
    return out


def _plan_tasks(store: Store, plan_ids: list[int]) -> dict[int, int]:
    """Task id -> milestone id for the plans in scope."""
    out: dict[int, int] = {}
    for plan_id in plan_ids:
        for milestone in store.list_milestones(plan_id):
            for task in store.list_tasks(milestone.id):
                out[task.id] = milestone.id
    return out


def _links(store: Store, plan_ids: list[int]) -> tuple[dict[str, set[int]], set[str]]:
    """Commit SHA -> owning task ids, plus every linked SHA for coverage."""
    tasks = _plan_tasks(store, plan_ids)
    by_sha: dict[str, set[int]] = {}
    linked: set[str] = set()

    def absorb(kind: str, obj_id: int, owners: set[int]) -> None:
        for link in store.list_links(kind, obj_id):
            linked.add(link.sha)
            by_sha.setdefault(link.sha, set()).update(owners)

    for plan_id in plan_ids:
        absorb("plan", plan_id, set(tasks))
    for milestone_id in set(tasks.values()):
        owners = {task_id for task_id, mid in tasks.items() if mid == milestone_id}
        absorb("milestone", milestone_id, owners)
    for task_id in tasks:
        absorb("task", task_id, {task_id})
    return by_sha, linked


def _gaps(store: Store, plan_ids: list[int], since: float = 0.0) -> list[Gap]:
    """Open criteria on rows done inside the window (all rows when since is 0)."""
    done = _done_times(store)

    def closed_in_window(kind: str, obj_id: int) -> bool:
        when = done.get((kind, obj_id))
        return since == 0.0 or (when is not None and when >= since)

    out: list[Gap] = []
    for plan_id in plan_ids:
        plan = store.get_plan(plan_id)
        if plan is not None and plan.status == Status.DONE and closed_in_window("plan", plan.id):
            out.extend(
                Gap("plan", plan.id, item.text) for item in store.open_criteria("plan", plan.id)
            )
        for milestone in store.list_milestones(plan_id):
            if milestone.status == Status.DONE and closed_in_window("milestone", milestone.id):
                out.extend(
                    Gap("milestone", milestone.id, item.text)
                    for item in store.open_criteria("milestone", milestone.id)
                )
            for task in store.list_tasks(milestone.id):
                if task.status == Status.DONE and closed_in_window("task", task.id):
                    out.extend(
                        Gap("task", task.id, item.text)
                        for item in store.open_criteria("task", task.id)
                    )
    return out


def _status_after(
    times: dict[int, list[tuple[float, Status]]], task_id: int, after: int
) -> float | None:
    """Earliest doing/done event at or after one commit."""
    candidates = [
        ts for ts, status in times.get(task_id, []) if ts >= after and status != Status.TODO
    ]
    return min(candidates) if candidates else None


def _lag(
    commits: list[Commit],
    linked: list[Commit],
    owners: dict[str, set[int]],
    times: dict[int, list[tuple[float, Status]]],
) -> tuple[list[float], list[float], int]:
    """Median-friendly lags in intervening commits and minutes, plus misses."""
    lag_commits: list[float] = []
    lag_minutes: list[float] = []
    unresolved = 0
    for commit in linked:
        status_ts = None
        for task_id in sorted(owners.get(commit.sha, ())):
            found = _status_after(times, task_id, commit.timestamp)
            if found is not None and (status_ts is None or found < status_ts):
                status_ts = found
        if status_ts is None:
            unresolved += 1
            continue
        lag_minutes.append((status_ts - commit.timestamp) / 60.0)
        intervening = sum(
            1
            for other in commits
            if other.repo == commit.repo and commit.timestamp < other.timestamp <= status_ts
        )
        lag_commits.append(float(intervening))
    return lag_commits, lag_minutes, unresolved


def compute(
    store: Store,
    plan_ids: list[int],
    commits: list[Commit],
    since: float = 0.0,
    repos: list[str] | None = None,
) -> Report:
    """Build a report from an explicit commit list; no writes and no git calls."""
    unique = {commit.sha: commit for commit in commits if commit.parents <= 1}
    ordered = sorted(unique.values(), key=lambda item: (item.timestamp, item.sha))
    owners, linked = _links(store, plan_ids)
    linked_commits = [commit for commit in ordered if commit.sha in linked]
    lag_commits, lag_minutes, unresolved = _lag(
        ordered, linked_commits, owners, _status_times(store)
    )
    return Report(
        plans=list(plan_ids),
        since=since,
        repos=list(repos or []),
        commits_total=len(ordered),
        commits_linked=len(linked_commits),
        lag_commits=lag_commits,
        lag_minutes=lag_minutes,
        unresolved=unresolved,
        gaps=_gaps(store, plan_ids, since),
    )


def _repo_paths(store: Store, plan_ids: list[int], cwd: str | Path) -> list[str]:
    """Linked checkout paths, or cwd when the plans have no repo links."""
    seen: list[str] = []
    for plan_id in plan_ids:
        for repo in store.effective_repos("plan", plan_id):
            path = str(repo.get("repo_path") or "")
            if path and path not in seen:
                seen.append(path)
    return seen or [str(Path(cwd).expanduser())]


def gather_commits(
    store: Store, plan_ids: list[int], since: float, cwd: str | Path = "."
) -> tuple[list[Commit], list[str]]:
    """Read non-merge commits from every effective repo after `since`."""
    repos = _repo_paths(store, plan_ids, cwd)
    stamp = datetime.fromtimestamp(since, UTC).isoformat()
    out: list[Commit] = []
    for path in repos:
        backend, root = vcs.detect_backend(path)
        if backend is None or root is None:
            continue
        try:
            history = backend.log(root, limit=1000, since=stamp)
        except (OSError, RuntimeError):
            continue
        for info in history:
            if len(info.parents) > 1:
                continue
            out.append(Commit(info.sha, info.timestamp, str(root), len(info.parents), info.subject))
    return out, repos


def report(
    store: Store,
    plan_ids: list[int] | None = None,
    since: float | None = None,
    cwd: str | Path = ".",
) -> Report:
    """Audit live: resolve the window, read git, then compute."""
    starts = plan_starts(store)
    if plan_ids is None:
        if since is None:
            known = [start for start in starts.values() if start > 0]
            since = min(known) if known else 0.0
        plans = [
            plan.id
            for plan in store.list_plans()
            if plan.status == Status.DOING or starts.get(plan.id, 0.0) >= since
        ]
    else:
        plans = list(plan_ids)
        if since is None:
            known = [starts[plan_id] for plan_id in plans if plan_id in starts]
            since = min(known) if known else 0.0
    commits, repos = gather_commits(store, plans, since, cwd)
    return compute(store, plans, commits, since=since, repos=repos)


def linked_shas(store: Store, plan_ids: list[int]) -> set[str]:
    """Every commit SHA already owned by a row in these plans."""
    return _links(store, plan_ids)[1]


def unlinked_commits(
    store: Store,
    plan_ids: list[int],
    since: float,
    cwd: str | Path = ".",
) -> list[Commit]:
    """Non-merge commits in the window that no row in scope owns, newest first."""
    commits, _repos = gather_commits(store, plan_ids, since, cwd)
    linked = linked_shas(store, plan_ids)
    unique = {commit.sha: commit for commit in commits if commit.parents <= 1}
    loose = [commit for sha, commit in unique.items() if sha not in linked]
    return sorted(loose, key=lambda commit: commit.timestamp, reverse=True)
