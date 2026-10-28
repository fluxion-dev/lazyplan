"""Tree services."""

from __future__ import annotations

import re
import time
from pathlib import Path

from ..models import Criterion, Milestone, Plan, Status, Task
from ..store import Store
from .base import (
    ARCHIVE_AFTER_SECS,
)

DEFAULT_PLAN_LIMIT = 5


def is_archived(store: Store, plan: Plan) -> bool:
    """Done longer than a day, with history to prove it. No proof: never hide."""
    return _is_archived(plan, store.plan_status_events_map(), time.time())


def _is_archived(plan: Plan, events: dict[int, tuple[float, str]], now: float) -> bool:
    """Archive decision from a preloaded latest-status map."""
    if plan.status != Status.DONE:
        return False
    last = events.get(plan.id)
    if last is None:
        return False
    ts, target = last
    return target == Status.DONE.value and (now - ts) > ARCHIVE_AFTER_SECS


def _plan_activity(
    milestones: dict[int, list[Milestone]],
    tasks: dict[int, list[Task]],
    criteria: dict[tuple[str, int], list[Criterion]],
    events: list[dict],
) -> dict[int, float]:
    """Latest event timestamp per plan from preloaded maps and events."""
    mplan: dict[int, int] = {
        milestone.id: milestone.plan_id for items in milestones.values() for milestone in items
    }
    tms: dict[int, int] = {task.id: task.milestone_id for items in tasks.values() for task in items}
    crit: dict[int, tuple[str, int]] = {
        criterion.id: (criterion.parent_kind, criterion.parent_id)
        for items in criteria.values()
        for criterion in items
    }

    def resolve(kind: str, detail: str) -> int | None:
        m = re.match(r"([PMT])#(\d+)", detail)
        if m:
            letter, oid = m.group(1), int(m.group(2))
            if letter == "P":
                return oid
            if letter == "M":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"(plan|milestone|task) #(\d+)", detail)
        if m:
            kind, oid = m.group(1), int(m.group(2))
            if kind == "plan":
                return oid
            if kind == "milestone":
                return mplan.get(oid)
            chained = tms.get(oid)
            return mplan.get(chained) if chained is not None else None
        m = re.match(r"criteria #(\d+)", detail)
        if m:
            found = crit.get(int(m.group(1)))
            if found is None:
                return None
            ckind, pid = found
            if ckind == "plan":
                return pid
            if ckind == "milestone":
                return mplan.get(pid)
            chained = tms.get(pid)
            return mplan.get(chained) if chained is not None else None
        return None

    out: dict[int, float] = {}
    for event in events:
        pid = resolve(str(event["kind"]), str(event["detail"] or ""))
        if pid is not None and event["ts"] > out.get(pid, 0.0):
            out[pid] = event["ts"]
    return out


def plan_activity(store: Store) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    return _plan_activity(
        store.milestones_map(),
        store.tasks_map(),
        store.criteria_map(),
        store.feed(limit=1_000_000),
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
    """Whether a plan survives status/archive filters."""
    if archived == "only" and not archived_now:
        return False
    if archived == "hide" and archived_now:
        return False
    if status is not None and plan.status != status and not milestones:
        return False
    return True


def tree(
    store: Store,
    status: Status | None = None,
    plan_id: int | None = None,
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters.

    archived: "hide" (default views), "only" (--archived), "show" (--status all).
    Plans order most-recently-active first (id fallback); limit caps the
    plan count (None = all). An explicit plan_id bypasses the cap.
    repo: only plans (or descendants) effectively linked to this repo.
    milestone_id: only this milestone (and its tasks) inside each plan.
    """
    if archived not in ("hide", "only", "show"):
        raise ValueError("archived must be hide|only|show")
    plans = store.list_plans()
    milestones = store.milestones_map()
    tasks = store.tasks_map()
    status_events = store.plan_status_events_map() if archived != "show" else {}
    repos = store.repos_map() if repo else {}
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
            store.criteria_map(),
            store.feed(limit=1_000_000),
        )
        out.sort(key=lambda entry: (activity.get(entry[0].id, 0.0), entry[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out
