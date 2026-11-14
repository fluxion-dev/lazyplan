"""Read-only verification for a registered plan worktree."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Milestone, Plan, PlanWorktree, Status
from ..core.policies.worktrees import derive_lane_worktree, quote_path
from ..core.ports.planning import PlanningPort
from ..core.ports.repos import ReposPort
from ..infrastructure.repo import git_common_dir, git_worktree_paths
from ..infrastructure.vcs import GitBackend


@dataclass(frozen=True)
class WorktreeVerification:
    """The outcome of checking one worktree against its linked checkout."""

    ok: bool
    reason: str = ""
    branch: str = ""
    head: str = ""
    dirty: bool = False


def _refuse(
    reason: str, branch: str = "", head: str = "", dirty: bool = False
) -> WorktreeVerification:
    return WorktreeVerification(False, reason=reason, branch=branch, head=head, dirty=dirty)


def lane_worktree_entries(store: ReposPort, plan: Plan, milestone: Milestone) -> list[dict]:
    """Derived, registered, and command-ready checkouts for one lane."""
    repos = store.list_repos("plan", plan.id)
    all_rows = store.list_plan_worktrees(plan.id)
    rows = [row for row in all_rows if row.milestone_id == milestone.id]
    if not rows and plan.dispatch_mode != "parallel":
        rows = [row for row in all_rows if row.milestone_id is None]
    entries: list[dict] = []
    for repo in repos:
        repo_path = str(repo["repo_path"])
        target = derive_lane_worktree(repo_path, plan.id, plan.name, milestone.id, milestone.title)
        registered = any(
            store.normalize_repo_path(row.repo_path) == store.normalize_repo_path(repo_path)
            for row in rows
        )
        base = str(repo.get("base_sha") or repo.get("branch") or "HEAD")
        entries.append(
            {
                "repo_path": target.repo_path,
                "worktree_path": target.worktree_path,
                "branch": target.branch,
                "registered": registered,
                "exists": os.path.exists(target.worktree_path),
                "git_command": (
                    f"git -C {quote_path(target.repo_path)} worktree add -b"
                    f" {target.branch} {quote_path(target.worktree_path)}"
                    f" {quote_path(base)}"
                ),
                "register_command": (
                    f"lpui plan worktree add --id {plan.id}"
                    f" --milestone {milestone.id} --repo {quote_path(target.repo_path)}"
                ),
            }
        )
    return entries


def lane_busy(store: PlanningPort, task_id: int) -> str:
    """Refusal text when another task is already doing in the same lane."""
    task = store.get_task(task_id)
    if task is None:
        return ""
    milestone = store.get_milestone(task.milestone_id)
    if milestone is None:
        return ""
    plan = store.get_plan(milestone.plan_id)
    if plan is None or plan.dispatch_mode != "parallel":
        return ""
    for other in store.list_tasks(milestone.id):
        if other.id == task_id or other.status is not Status.DOING:
            continue
        get_claim = getattr(store, "get_claim", None)
        held = get_claim(other.id) if get_claim is not None else None
        holder = held.actor if held is not None else "another agent"
        return (
            f"lane M{milestone.id} already has T{other.id} doing by {holder};"
            f" finish it or use `lpui claim --id {task_id} --force --reason TEXT`"
        )
    return ""


def worktree_gate(store: ReposPort, plan_id: int) -> str:
    """Refusal text when an isolation-required plan is missing a worktree."""
    plan = store.get_plan(plan_id)
    if plan is None or not plan.worktree_required:
        return ""
    repos = store.repos_map().get(("plan", plan_id), [])
    if not repos:
        return (
            f"plan #{plan_id} requires isolation but has no linked repo;"
            f" run `lpui plan worktree --print --id {plan_id}`"
        )
    registered_paths = {
        os.path.normcase(os.path.abspath(row.repo_path))
        for row in store.list_plan_worktrees(plan_id)
    }
    missing = [
        str(row["repo_path"])
        for row in repos
        if os.path.normcase(os.path.abspath(str(row["repo_path"]))) not in registered_paths
    ]
    if missing:
        return (
            f"plan #{plan_id} requires a registered worktree for: {', '.join(missing)};"
            f" run `lpui plan worktree --print --id {plan_id}`"
        )
    if plan.dispatch_mode == "parallel":
        lanes = {row.milestone_id for row in store.list_plan_worktrees(plan_id)}
        missing_lanes = [
            milestone.id
            for milestone in store.list_milestones(plan_id)
            if milestone.id not in lanes
        ]
        if missing_lanes:
            names = ", ".join(f"M{row}" for row in missing_lanes)
            first = missing_lanes[0]
            return (
                f"plan #{plan_id} requires a registered worktree for lanes: {names};"
                f" run `lpui plan worktree print --id {plan_id} --milestone {first}`"
            )
    return ""


def lane_gate(store: PlanningPort, task_id: int, checkout: str) -> str:
    """Refusal text when a task must run in a different lane checkout."""
    if not checkout.strip():
        return ""
    task = store.get_task(task_id)
    if task is None:
        return ""
    milestone = store.get_milestone(task.milestone_id)
    if milestone is None:
        return ""
    plan = store.get_plan(milestone.plan_id)
    if plan is None or not plan.worktree_required or plan.dispatch_mode != "parallel":
        return ""
    rows = store.list_plan_worktrees(plan.id)
    lane_rows = [row for row in rows if row.milestone_id == milestone.id]
    if not lane_rows:
        return (
            f"lane M{milestone.id} of plan #{plan.id} has no registered worktree;"
            f" run `lpui plan worktree print --id {plan.id} --milestone {milestone.id}`"
        )
    current = os.path.normcase(os.path.abspath(checkout))
    if any(os.path.normcase(os.path.abspath(row.worktree_path)) == current for row in lane_rows):
        return ""
    other = next(
        (
            row
            for row in rows
            if row.milestone_id is not None
            and os.path.normcase(os.path.abspath(row.worktree_path)) == current
        ),
        None,
    )
    if other is not None:
        return (
            f"this checkout is lane M{other.milestone_id};"
            f" task #{task_id} belongs to lane M{milestone.id}"
        )
    expected = ", ".join(row.worktree_path for row in lane_rows)
    return f"task #{task_id} must run in lane M{milestone.id}: {expected}"


def checkout_gate(store: ReposPort, plan_id: int, checkout: str) -> str:
    """Refusal text when a session starts outside the plan's registered worktree."""
    plan = store.get_plan(plan_id)
    if plan is None or not plan.worktree_required:
        return ""
    blocker = worktree_gate(store, plan_id)
    if blocker:
        return blocker
    current = os.path.normcase(os.path.abspath(checkout))
    registered = store.list_plan_worktrees(plan_id)
    if any(os.path.normcase(os.path.abspath(row.worktree_path)) == current for row in registered):
        return ""
    expected = ", ".join(row.worktree_path for row in registered)
    return f"session start must run in a registered worktree: {expected}"


def stale_reason(row: PlanWorktree) -> str:
    """Why a registration no longer points at a live worktree; empty when current."""
    path = row.worktree_path
    if not Path(path).exists():
        return "registered worktree path does not exist"
    listed = git_worktree_paths(row.repo_path)
    current = str(Path(path).resolve())
    if listed and current not in listed:
        return "registered worktree is not listed by git worktree list"
    return ""


def done_blocker(store: PlanningPort, plan_id: int) -> str:
    """Refusal text when a registered worktree cannot be closed out cleanly."""
    for row in store.list_plan_worktrees(plan_id):
        if not Path(row.worktree_path).exists():
            continue
        check = verify_worktree(row.repo_path, row.worktree_path, row.branch)
        if not check.ok:
            return f"plan #{plan_id} worktree {row.worktree_path}: {check.reason}"
    return ""


def removal_commands(store: PlanningPort, plan_id: int) -> list[str]:
    """Read-only removal commands printed when a plan closes."""
    return [
        f"git -C {quote_path(row.repo_path)} worktree remove {quote_path(row.worktree_path)}"
        for row in store.list_plan_worktrees(plan_id)
    ]


def verify_worktree(repo_path: str, worktree_path: str, branch: str) -> WorktreeVerification:
    """Check that *worktree_path* is this repo's checkout on *branch* and clean."""
    if os.path.normcase(os.path.abspath(repo_path)) == os.path.normcase(
        os.path.abspath(worktree_path)
    ):
        return _refuse("worktree path must differ from the linked checkout")

    repo_common = git_common_dir(repo_path)
    if not repo_common:
        return _refuse(f"linked checkout is not a git repository: {repo_path}")
    worktree_common = git_common_dir(worktree_path)
    if not worktree_common:
        return _refuse(f"worktree is not a git checkout: {worktree_path}")
    if os.path.normcase(repo_common) != os.path.normcase(worktree_common):
        return _refuse("worktree belongs to a different repository")

    status = GitBackend().status(worktree_path)
    if status.detached or not status.branch:
        return _refuse("worktree has a detached HEAD", head=status.head, dirty=status.dirty)
    if status.branch != branch:
        return _refuse(
            f"worktree is on branch {status.branch!r}, expected {branch!r}",
            branch=status.branch,
            head=status.head,
            dirty=status.dirty,
        )
    if status.dirty:
        return _refuse(
            "worktree has uncommitted changes",
            branch=status.branch,
            head=status.head,
            dirty=True,
        )
    return WorktreeVerification(True, branch=status.branch, head=status.head)
