"""Read-only dispatch manifest: waves, lanes, capacity, and worker prompts."""

from __future__ import annotations

import os
import time
from typing import Any

from ..core.entities import Claim, Milestone, Plan, Task
from ..core.policies.worktrees import derive_lane_worktree, quote_path
from ..core.ports.insights import InsightsPort

DEFAULT_MAX_CHARS = 4000


def build(
    store: InsightsPort,
    plan_id: int,
    lane_id: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Build the dispatch manifest for one plan without writing anything."""
    plan = store.get_plan(plan_id)
    if plan is None:
        raise KeyError(f"plan #{plan_id} not found")
    milestones = store.list_milestones(plan_id)
    if lane_id is not None and all(item.id != lane_id for item in milestones):
        raise ValueError(f"milestone #{lane_id} is not in plan #{plan_id}")
    tasks_by = {milestone.id: store.list_tasks(milestone.id) for milestone in milestones}
    claims = store.claims_map()
    now = time.time()
    groups = _groups(milestones)
    done_groups = {group: _group_done(milestones, tasks_by, group) for group in groups}
    current = next((group for group in groups if not done_groups[group]), None)
    cap = plan.max_agents if plan.dispatch_mode == "parallel" else 1

    lanes: list[dict[str, Any]] = []
    next_by_lane: dict[int, Task | None] = {}
    for milestone in milestones:
        tasks = tasks_by[milestone.id]
        claim = next(
            (
                claims[task.id]
                for task in tasks
                if task.id in claims
                and task.status.value == "doing"
                and not claims[task.id].expired(now)
            ),
            None,
        )
        worktrees = _worktrees(store, plan, milestone)
        lane_next = next(
            (task for task in tasks if task.status.value == "todo" and not task.blocked),
            None,
        )
        next_by_lane[milestone.id] = lane_next
        state = _state(milestone, tasks, worktrees, claim, current)
        blocked = _lane_blockers(milestone, tasks, worktrees, claim, current)
        prompt = (
            _prompt(plan, milestone, lane_next, worktrees, max_chars)
            if lane_next is not None
            else ""
        )
        lanes.append(
            {
                "milestone_id": milestone.id,
                "title": milestone.title,
                "group": milestone.lane_group,
                "agent_role": milestone.agent_role,
                "state": state,
                "worktrees": worktrees,
                "tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "role": task.role,
                        "status": task.status.value,
                        "blocked": task.blocked,
                        "touchpoints": store.list_touchpoints(task.id),
                    }
                    for task in tasks
                ],
                "claim": _claim_payload(claim),
                "next": (
                    {"id": lane_next.id, "title": lane_next.title, "role": lane_next.role}
                    if lane_next is not None
                    else None
                ),
                "blocked": blocked,
                "prompt": prompt,
            }
        )

    milestone_by_id = {milestone.id: milestone for milestone in milestones}
    selected = [lane for lane in lanes if lane_id is None or lane["milestone_id"] == lane_id]
    active = sum(1 for lane in lanes if lane["claim"] is not None)
    available = max(0, cap - active) if current is not None else 0
    if lane_id is not None:
        available = min(available, 1)
    dispatchable: list[dict[str, Any]] = []
    for lane in selected:
        if len(dispatchable) >= available:
            break
        task = next_by_lane[lane["milestone_id"]]
        if lane["state"] != "ready" or lane["claim"] is not None or task is None:
            continue
        dispatchable.append(
            _dispatchable(
                plan,
                milestone_by_id[lane["milestone_id"]],
                lane,
                task,
                max_chars,
            )
        )
    actions = _actions(lanes, dispatchable)
    top_blocked = _top_blockers(store, plan, milestones)
    return {
        "plan": {
            "id": plan.id,
            "title": plan.name,
            "status": plan.status.value,
            "dispatch_mode": plan.dispatch_mode,
            "max_agents": plan.max_agents,
            "worktree_required": plan.worktree_required,
        },
        "capacity": {"max": cap, "active": active, "available": available},
        "wave": current,
        "waves": _waves(groups, lanes, current),
        "lanes": selected,
        "dispatchable": dispatchable,
        "actions": actions,
        "blocked": top_blocked,
    }


def _groups(milestones: list[Milestone]) -> list[int]:
    """Wave numbers in ascending order."""
    return sorted({milestone.lane_group for milestone in milestones})


def _group_done(milestones: list[Milestone], tasks_by: dict[int, list[Task]], group: int) -> bool:
    """True when every task in one wave is done."""
    for milestone in milestones:
        if milestone.lane_group != group:
            continue
        tasks = tasks_by[milestone.id]
        if not tasks or any(task.status.value != "done" for task in tasks):
            return False
    return True


def _state(
    milestone: Milestone,
    tasks: list[Task],
    worktrees: list[dict[str, Any]],
    claim: object,
    current: int | None,
) -> str:
    """One lane state word."""
    if milestone.status.value == "done" or (
        tasks and all(task.status.value == "done" for task in tasks)
    ):
        return "done"
    if any(task.blocked for task in tasks):
        return "blocked"
    if claim is not None:
        return "active"
    if milestone.lane_group != current:
        return "waiting"
    if not tasks:
        return "empty"
    if not worktrees:
        return "blocked"
    if any(not row["registered"] for row in worktrees):
        return "unregistered"
    if not any(task.status.value == "todo" and not task.blocked for task in tasks):
        return "blocked"
    return "ready"


def _lane_blockers(
    milestone: Milestone,
    tasks: list[Task],
    worktrees: list[dict[str, Any]],
    claim: object,
    current: int | None,
) -> list[str]:
    """Why a lane cannot dispatch right now; empty when it can."""
    blocked: list[str] = []
    if claim is not None:
        blocked.append("a task is already doing in this lane")
    if milestone.lane_group != current:
        blocked.append(f"wave {milestone.lane_group} waits for wave {current}")
    if not tasks:
        blocked.append("lane has no tasks")
    if not worktrees:
        blocked.append("plan has no linked repo")
    for row in worktrees:
        if not row["registered"]:
            blocked.append(f"worktree is not registered: {row['repo_path']}")
    if tasks and not any(task.status.value == "todo" and not task.blocked for task in tasks):
        blocked.append("no todo task is ready")
    if any(task.blocked for task in tasks):
        blocked.append("a task is blocked")
    return blocked


def _worktrees(store: InsightsPort, plan: Plan, milestone: Milestone) -> list[dict[str, Any]]:
    """Derived and registered checkouts for one lane."""
    repos = store.list_repos("plan", plan.id)
    all_rows = store.list_plan_worktrees(plan.id)
    rows = [row for row in all_rows if row.milestone_id == milestone.id]
    if not rows and plan.dispatch_mode != "parallel":
        rows = [row for row in all_rows if row.milestone_id is None]
    entries: list[dict[str, Any]] = []
    for repo in repos:
        repo_path = str(repo["repo_path"])
        target = derive_lane_worktree(repo_path, plan.id, plan.name, milestone.id, milestone.title)
        registered = next(
            (
                row
                for row in rows
                if store.normalize_repo_path(row.repo_path) == store.normalize_repo_path(repo_path)
            ),
            None,
        )
        base = str(repo.get("base_sha") or repo.get("branch") or "HEAD")
        entries.append(
            {
                "repo_path": target.repo_path,
                "worktree_path": target.worktree_path,
                "branch": target.branch,
                "registered": registered is not None,
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


def _claim_payload(claim: Claim | None) -> dict[str, Any] | None:
    """One claim as a JSON-safe dict."""
    if claim is None:
        return None
    return {
        "task_id": claim.task_id,
        "actor": claim.actor,
        "expires_at": claim.expires_at,
    }


def _dispatchable(
    plan: Plan,
    milestone: Milestone,
    lane: dict[str, Any],
    task: Task,
    max_chars: int,
) -> dict[str, Any]:
    """One ready task with its lane, worktree, claim, and prompt."""
    registered = [row for row in lane["worktrees"] if row["registered"]]
    primary = (registered or lane["worktrees"] or [{}])[0]
    path = str(primary.get("worktree_path") or "")
    branch = str(primary.get("branch") or "")
    return {
        "lane_id": lane["milestone_id"],
        "task_id": task.id,
        "title": task.title,
        "role": task.role,
        "agent_role": lane["agent_role"],
        "worktree": path,
        "branch": branch,
        "worktrees": lane["worktrees"],
        "claim_command": (
            f"lpui claim --id {task.id} --worktree {quote_path(path)}" if path else ""
        ),
        "prompt": _prompt(plan, milestone, task, lane["worktrees"], max_chars),
    }


def _prompt(
    plan: Plan,
    milestone: Milestone,
    task: Task | None,
    worktrees: list[dict[str, Any]],
    max_chars: int,
) -> str:
    """A bounded worker prompt for one lane task."""
    if task is None:
        return ""
    paths = [row["worktree_path"] for row in worktrees if row["registered"]] or [
        row["worktree_path"] for row in worktrees
    ]
    branches = [row["branch"] for row in worktrees if row["registered"]] or [
        row["branch"] for row in worktrees
    ]
    lines = [
        f"Lane M{milestone.id} {milestone.title!r}, wave {milestone.lane_group},"
        f" role {milestone.agent_role}, plan P{plan.id} {plan.name!r}.",
        f"Work only in {', '.join(paths) or 'the lane checkout'}"
        f" on {', '.join(branches) or 'the lane branch'}.",
        f"Task T{task.id}: {task.title} ({task.role}).",
        task.description,
        "Commit small green slices and link each with"
        f" `lpui link --kind task --id {task.id}`; note handoffs; finish with"
        f" `lpui task finish --id {task.id}`.",
    ]
    text = "\n\n".join(part for part in lines if part.strip())
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)].rstrip() + "…"


def _waves(
    groups: list[int], lanes: list[dict[str, Any]], current: int | None
) -> list[dict[str, Any]]:
    """Wave summaries in group order."""
    waves = []
    for group in groups:
        members = [lane["milestone_id"] for lane in lanes if lane["group"] == group]
        states = {lane["state"] for lane in lanes if lane["group"] == group}
        if states <= {"done"}:
            state = "done"
        elif "active" in states:
            state = "active"
        elif group == current:
            state = "ready"
        else:
            state = "waiting"
        waves.append({"group": group, "state": state, "lanes": members})
    return waves


def _top_blockers(store: InsightsPort, plan: Plan, milestones: list[Milestone]) -> list[str]:
    """Plan-level reasons the orchestrator cannot dispatch anything."""
    blocked: list[str] = []
    if plan.status.value != "doing":
        blocked.append(f"plan #{plan.id} is {plan.status.value}, not doing")
    if not milestones:
        blocked.append("plan has no milestones")
    if not store.list_repos("plan", plan.id):
        blocked.append("plan has no linked repo")
    if plan.dispatch_mode == "parallel" and plan.max_agents < 2:
        blocked.append("parallel plan needs max_agents >= 2")
    return blocked


def _actions(lanes: list[dict[str, Any]], dispatchable: list[dict[str, Any]]) -> list[str]:
    """Ordered commands the orchestrator runs next."""
    actions: list[str] = []
    for lane in lanes:
        for row in lane["worktrees"]:
            if row["registered"]:
                continue
            if not row["exists"]:
                actions.append(row["git_command"])
            actions.append(row["register_command"])
    for item in dispatchable:
        if item["claim_command"]:
            actions.append(item["claim_command"])
    seen: set[str] = set()
    unique: list[str] = []
    for action in actions:
        if action in seen:
            continue
        seen.add(action)
        unique.append(action)
    return unique
