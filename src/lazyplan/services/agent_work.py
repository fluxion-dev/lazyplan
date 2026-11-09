"""Start and finish one agent work session against a task."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..infrastructure.vcs import detect_backend
from ..store import Store
from . import sessions as session_service
from .coordination import start_claim


def _branch(cwd: str | Path) -> str:
    try:
        backend, root = detect_backend(cwd)
        if backend is not None and root is not None:
            return backend.status(root).branch
    except (OSError, RuntimeError):
        pass
    return ""


def work_prompt(store: Store, task_id: int, branch: str = "") -> str:
    """Build the first prompt for a task work session."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task {task_id} not found")
    milestone = store.get_milestone(task.milestone_id)
    plan = store.get_plan(milestone.plan_id) if milestone is not None else None
    criteria = store.list_criteria("task", task_id)
    lines = [
        f"Work on T{task_id} {task.title}.",
        "",
        f"Plan: {plan.name if plan is not None else 'unknown'}",
        f"Milestone: {milestone.title if milestone is not None else 'unknown'}",
        f"Branch: {branch or 'current checkout'}",
        "",
        "Description:",
        task.description or "(none)",
        "",
        "Acceptance criteria:",
    ]
    if criteria:
        lines.extend(f"- {criterion.text}" for criterion in criteria)
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "Use the lazyplan MCP tools to claim the task, record notes, and finish it.",
            "Keep the human in the loop for structural changes and permissions.",
        ]
    )
    return "\n".join(lines)


def start_work(
    store: Store,
    task_id: int,
    *,
    actor: str,
    cwd: str | Path,
) -> dict[str, Any]:
    """Claim a task, open a lazyplan session, and return the work prompt."""
    task = store.get_task(task_id)
    if task is None:
        raise KeyError(f"task {task_id} not found")
    milestone = store.get_milestone(task.milestone_id)
    if milestone is None:
        raise KeyError(f"milestone {task.milestone_id} not found")
    plan = store.get_plan(milestone.plan_id)
    if plan is None:
        raise KeyError(f"plan {milestone.plan_id} not found")
    branch = _branch(cwd)
    start_claim(store, task_id, actor, ttl="1h", note="agent workbench")
    opened = session_service.start_session(
        store,
        actor,
        plan_id=plan.id,
        repo_path=str(Path(cwd).expanduser().resolve()),
        branch=branch,
    )
    return {
        "task": task,
        "milestone": milestone,
        "plan": plan,
        "session": opened["session"],
        "branch": branch,
        "prompt": work_prompt(store, task_id, branch),
    }


def finish_work(
    store: Store,
    run_id: int,
    *,
    actor: str,
    summary: str = "",
    handoff: str = "",
) -> dict[str, Any]:
    """Close the agent run and its lazyplan session."""
    run = store.get_agent_run(run_id)
    if run is None:
        raise KeyError(f"agent run #{run_id} not found")
    session_id = run["lazyplan_session_id"]
    if isinstance(session_id, int):
        try:
            session_service.end_session(
                store,
                session_id,
                actor,
                summary=summary,
                handoff=handoff,
            )
        except (KeyError, ValueError):
            pass
    return store.end_agent_run(
        run_id,
        status="done",
        summary=summary,
        handoff=handoff,
        actor=actor,
    )
