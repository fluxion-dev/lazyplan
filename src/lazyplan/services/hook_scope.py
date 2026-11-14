"""Which checkout a hook may gate, and which task owns it.

A hook must never turn an unrelated repository into a gated one. The checkout
is managed only when the database lives in that checkout, a row links the
checkout, or a live claim was taken in it. The
owning task is the first doing task under a doing plan that resolves to the
same checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Milestone, Plan, Status, Task
from ..core.ports.app import AppPort
from ..core.ports.planning import PlanningPort
from . import coordination
from .worktrees import lane_registrations

LOCAL_PARTS = (".agents", "lazyplan")


@dataclass(frozen=True)
class HookScope:
    """One checkout's gating context."""

    repo: str
    managed: bool = False
    task: Task | None = None

    @property
    def task_id(self) -> int | None:
        """Doing task id, or None."""
        return None if self.task is None else self.task.id


def _local_db(store: AppPort, repo: str) -> bool:
    """True when the database is the checkout's own repo-scoped journal."""
    return Path(store.db_path).resolve().parent == Path(repo).joinpath(*LOCAL_PARTS).resolve()


def _linked_rows(store: AppPort, repo: str) -> set[tuple[str, int]]:
    """Rows with an explicit repo link to this checkout."""
    wanted = store.normalize_repo_path(repo)
    linked: set[tuple[str, int]] = set()
    for (kind, row_id), links in store.repos_map().items():
        for link in links:
            if store.normalize_repo_path(str(link.get("repo_path", ""))) == wanted:
                linked.add((kind, row_id))
                break
    return linked


def _claimed_here(store: AppPort, repo: str, ignored: set[int]) -> bool:
    """True when a live claim was taken in this checkout.

    Claims for plans isolated in another worktree do not manage this checkout.
    """
    return any(
        int(claim["plan_id"]) not in ignored for claim in coordination.checkout_claims(store, repo)
    )


def _same_checkout(left: str, right: str, store: PlanningPort) -> bool:
    """True when two paths resolve to one checkout."""
    return store.normalize_repo_path(left) == store.normalize_repo_path(right)


def lane_for_checkout(
    store: PlanningPort, cwd: str | Path | None = None
) -> tuple[Plan, Milestone] | None:
    """The doing plan and lane registered at this checkout, if any."""
    repo = store.checkout_path(str(cwd or Path.cwd()))
    for plan in store.list_plans():
        if plan.status != Status.DOING:
            continue
        for row in lane_registrations(store, plan.id):
            if row.milestone_id is None:
                continue
            if not _same_checkout(row.worktree_path, repo, store):
                continue
            milestone = store.get_milestone(row.milestone_id)
            if milestone is not None:
                return plan, milestone
    return None


def _isolated_plans(store: AppPort, repo: str, doing: list[Plan]) -> tuple[set[int], set[int]]:
    """Plans registered in another worktree, and plans registered here."""
    ignored: set[int] = set()
    registered: set[int] = set()
    for plan in doing:
        if not plan.worktree_required:
            continue
        rows = store.list_plan_worktrees(plan.id)
        if not rows:
            continue
        if any(_same_checkout(row.worktree_path, repo, store) for row in rows):
            registered.add(plan.id)
        else:
            ignored.add(plan.id)
    return ignored, registered


def _doing_task(store: AppPort, plan_id: int) -> Task | None:
    """First doing task under one plan, if any."""
    for milestone in store.list_milestones(plan_id):
        for task in store.list_tasks(milestone.id):
            if task.status == Status.DOING:
                return task
    return None


def _claimed_task(store: AppPort, plan_id: int, repo: str) -> Task | None:
    """The doing task this checkout's live claim holds for one plan."""
    for claim in coordination.checkout_claims(store, repo):
        if int(claim.get("plan_id") or 0) != plan_id:
            continue
        task = store.get_task(int(claim["task_id"]))
        if task is not None and task.status == Status.DOING:
            return task
    return None


def _lane_task(store: AppPort, plan: Plan, repo: str) -> Task | None:
    """A doing task in a lane registered at this checkout, else the first doing."""
    if plan.dispatch_mode != "parallel":
        return _doing_task(store, plan.id)
    lanes = {
        row.milestone_id
        for row in lane_registrations(store, plan.id)
        if _same_checkout(row.worktree_path, repo, store)
    }
    for milestone in store.list_milestones(plan.id):
        if milestone.id not in lanes:
            continue
        for task in store.list_tasks(milestone.id):
            if task.status == Status.DOING:
                return task
    return None


def _plan_linked(store: AppPort, plan_id: int, linked: set[tuple[str, int]]) -> bool:
    """True when the plan or one of its milestones links this checkout."""
    if ("plan", plan_id) in linked:
        return True
    return any(
        ("milestone", milestone.id) in linked for milestone in store.list_milestones(plan_id)
    )


def resolve(store: AppPort, cwd: str | Path | None = None) -> HookScope:
    """Return the managed state and doing task for one checkout."""
    repo = store.checkout_path(str(cwd or Path.cwd()))
    doing = [plan for plan in store.list_plans() if plan.status == Status.DOING]
    ignored, registered = _isolated_plans(store, repo, doing)
    local = _local_db(store, repo)
    linked = {
        row for row in _linked_rows(store, repo) if not (row[0] == "plan" and row[1] in ignored)
    }
    managed = local or bool(linked) or bool(registered) or _claimed_here(store, repo, ignored)
    if not managed:
        return HookScope(repo=repo)

    for plan in doing:
        if plan.id in ignored:
            continue
        if not local and plan.id not in registered and not _plan_linked(store, plan.id, linked):
            continue
        task = _claimed_task(store, plan.id, repo) or _lane_task(store, plan, repo)
        if task is not None:
            return HookScope(repo=repo, managed=True, task=task)
    return HookScope(repo=repo, managed=True)
