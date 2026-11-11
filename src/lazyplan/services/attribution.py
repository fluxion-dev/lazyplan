"""Resolve the plan and branch a session runs under.

The caller supplies the checkout. Resolution reads git and journal rows
through the application port and never writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Status
from ..core.policies.provenance import branch_ref
from ..core.ports.app import AppPort
from ..infrastructure.vcs import detect_backend

LOCAL_DB_PARTS = (".agents", "lazyplan")


@dataclass(frozen=True)
class Attribution:
    """Plan and task a session's checkout points at."""

    plan_id: int | None = None
    task_id: int | None = None


def current_branch(repo_path: str) -> str:
    """Checked-out branch for one checkout; empty on a detached HEAD."""
    if not repo_path:
        return ""
    backend, root = detect_backend(repo_path)
    if backend is None or root is None:
        return ""
    try:
        return backend.branch(root) or ""
    except (OSError, RuntimeError, ValueError):
        return ""


def _plan_for_task(port: AppPort, task_id: int) -> Attribution | None:
    """Attribution for one task, through its milestone."""
    task = port.get_task(task_id)
    if task is None:
        return None
    milestone = port.get_milestone(task.milestone_id)
    if milestone is None:
        return None
    return Attribution(plan_id=milestone.plan_id, task_id=task.id)


def _from_branch_ref(port: AppPort, branch: str) -> Attribution | None:
    """Attribution encoded in a ``task/N``, ``plan/N``, or ``milestone/N`` name."""
    ref = branch_ref(branch)
    if ref is None:
        return None
    kind, row_id = ref
    if kind == "task":
        return _plan_for_task(port, row_id)
    if kind == "milestone":
        milestone = port.get_milestone(row_id)
        return None if milestone is None else Attribution(plan_id=milestone.plan_id)
    plan = port.get_plan(row_id)
    return None if plan is None else Attribution(plan_id=plan.id)


def _from_recorded_branch(port: AppPort, repo_path: str, branch: str) -> Attribution | None:
    """Attribution from a task that recorded this branch in this checkout."""
    if not branch:
        return None
    owners = port.branch_owners(repo_path, branch)
    return _plan_for_task(port, owners[0].id) if owners else None


def _same_checkout(port: AppPort, left: str, right: str) -> bool:
    """True when two paths name the same checkout."""
    if not left or not right:
        return False
    return port.normalize_repo_path(left) == port.normalize_repo_path(right)


def _from_claim(port: AppPort, repo_path: str) -> Attribution | None:
    """Newest active claim held in this checkout."""
    matches = [
        claim
        for claim in port.list_claims()
        if _same_checkout(port, str(claim.get("repo_path", "")), repo_path)
        or _same_checkout(port, str(claim.get("worktree", "")), repo_path)
    ]
    if not matches:
        return None
    claim = max(matches, key=lambda row: float(row.get("started_at", 0.0)))
    return Attribution(plan_id=int(claim["plan_id"]), task_id=int(claim["task_id"]))


def _linked_rows(port: AppPort, repo_path: str) -> set[tuple[str, int]]:
    """Rows with an explicit repo link to this checkout."""
    linked: set[tuple[str, int]] = set()
    for (kind, row_id), links in port.repos_map().items():
        if any(_same_checkout(port, str(link.get("repo_path", "")), repo_path) for link in links):
            linked.add((kind, row_id))
    return linked


def _local_db(port: AppPort, repo_path: str) -> bool:
    """True when the journal lives inside this checkout."""
    return (
        Path(port.db_path).resolve().parent == Path(repo_path).joinpath(*LOCAL_DB_PARTS).resolve()
    )


def _plan_linked(port: AppPort, linked: set[tuple[str, int]], plan_id: int) -> bool:
    """True when the plan or any child carries a repo link to this checkout."""
    if ("plan", plan_id) in linked:
        return True
    for milestone in port.list_milestones(plan_id):
        if ("milestone", milestone.id) in linked:
            return True
        if any(("task", task.id) in linked for task in port.list_tasks(milestone.id)):
            return True
    return False


def _from_doing_plan(port: AppPort, repo_path: str) -> Attribution | None:
    """The one doing plan that reaches this checkout, when it is unambiguous."""
    local = _local_db(port, repo_path)
    linked = set() if local else _linked_rows(port, repo_path)
    plans = [plan for plan in port.list_plans() if plan.status == Status.DOING]
    candidates = plans if local else [plan for plan in plans if _plan_linked(port, linked, plan.id)]
    if len(candidates) != 1:
        return None
    return Attribution(plan_id=candidates[0].id)


def resolve(
    port: AppPort,
    repo_path: str,
    branch: str = "",
    explicit_plan: int | None = None,
) -> Attribution:
    """Best plan and task for one checkout and branch.

    Precedence: explicit plan, branch ref, recorded branch, active claim,
    then the single doing plan scoped to this checkout.
    """
    if explicit_plan is not None:
        return Attribution(plan_id=explicit_plan)
    repo = port.normalize_repo_path(repo_path) if repo_path else ""
    steps = (
        lambda: _from_branch_ref(port, branch),
        lambda: _from_recorded_branch(port, repo, branch),
        lambda: _from_claim(port, repo),
        lambda: _from_doing_plan(port, repo),
    )
    for step in steps:
        found = step()
        if found is not None:
            return found
    return Attribution()
