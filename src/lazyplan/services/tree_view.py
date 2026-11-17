"""Recent-first plan tree reads: filters, ordering, and the activity sort."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Criterion, Milestone, Plan, Status, Task
from ..core.policies.insights import PLAN_EVENT_PREFIXES, plan_for_event
from ..core.policies.maintenance import check_archive_mode, is_visible
from ..core.policies.planning import is_archived as _is_archived_policy
from ..core.ports.planning import PlanningPort
from ..core.ports.repos import ReposPort


@dataclass(frozen=True)
class TreeSource:
    """The two reads the recent-first sort needs, when a caller already has them."""

    criteria: dict[tuple[str, int], list[Criterion]]
    events: list[dict]


def activity_source(
    port: PlanningPort,
    criteria: dict[tuple[str, int], list[Criterion]] | None = None,
) -> TreeSource:
    """Load the activity sort's inputs once for several tree reads.

    Events are oldest first so a caller can also feed them to the attention
    parser, which reads transitions in order.
    """
    return TreeSource(
        criteria=port.criteria_map() if criteria is None else criteria,
        events=list(reversed(port.events_by_prefix(PLAN_EVENT_PREFIXES, limit=100_000))),
    )


def plan_activity(port: PlanningPort) -> dict[int, float]:
    """Latest event timestamp per plan (whole subtree), for recent-first ordering."""
    return port.plan_activity_map()


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
    out: dict[int, float] = {}
    for event in events:
        plan_id = plan_for_event(
            str(event.get("detail") or ""),
            milestone_plan,
            task_milestone,
            criterion_parent,
        )
        if plan_id is None:
            continue
        stamp = float(event.get("ts") or 0.0)
        if stamp > out.get(plan_id, 0.0):
            out[plan_id] = stamp
    return out


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


def _is_finished(plan: Plan, events: dict[int, tuple[float, str]], now: float) -> bool:
    """Age-based finished decision from a preloaded latest-status map."""
    return _is_archived_policy(plan, events, now)


def tree(
    port: ReposPort,
    status: Status | None = None,
    plan_id: int | None = None,
    finished: str = "hide",
    archived: str = "hide",
    limit: int | None = None,
    repo: str | None = None,
    milestone_id: int | None = None,
    plan_mode: str = "all",
    source: TreeSource | None = None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """Nested plans, milestones, and tasks with filters."""
    check_archive_mode(finished)
    check_archive_mode(archived)
    if archived != "hide" and finished == "hide":
        finished = "show"
    if plan_mode not in ("all", "active", "finished"):
        raise ValueError("plan_mode must be all|active|finished")
    with port.transaction():
        return _tree_rows(
            port,
            status,
            plan_id,
            finished,
            archived,
            limit,
            repo,
            milestone_id,
            plan_mode,
            source,
        )


def _tree_rows(
    port: ReposPort,
    status: Status | None,
    plan_id: int | None,
    finished: str,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone_id: int | None,
    plan_mode: str,
    source: TreeSource | None,
) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
    """One tree snapshot; the caller owns the shared read transaction."""
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
        shared = source or activity_source(port)
        activity = _plan_activity(milestones, tasks, shared.criteria, shared.events)
        out.sort(key=lambda entry: (activity.get(entry[0].id, 0.0), entry[0].id), reverse=True)
        if limit is not None:
            out = out[: max(limit, 0)]
    return out
