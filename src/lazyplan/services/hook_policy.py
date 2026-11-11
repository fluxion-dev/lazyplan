"""Strict hook decisions: commit, stop, session end, and edit nudges.

The dispatch in :mod:`hooks` supplies payload text and the current session.
These functions decide whether a managed checkout should block, remind, or
stay silent. They never write except to close a session on session end.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from ..core.entities import HookResult, Session
from ..core.ports.app import AppPort
from ..core.ports.insights import InsightsPort
from . import audit, brief, hook_scope
from . import sessions as session_services


def _brief_lines(store: InsightsPort, cwd: Path, commits: list[audit.Commit] | None) -> list[str]:
    """Project brief lines for one checkout and commit window."""
    payload = brief.build(store, commits=commits, cwd=cwd)
    return brief.lines(payload)


def _doing_task(store: InsightsPort) -> int | None:
    """First doing task id across every plan."""
    for plan in store.list_plans():
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                if task.status.value == "doing":
                    return task.id
    return None


def _matches_task(path: str, patterns: list[str]) -> bool:
    """True when a path belongs to one of a task's touch-points."""
    name = Path(path).name
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def stop_result(
    store: AppPort,
    cwd: Path,
    commits: list[audit.Commit] | None,
    session: Session | None,
    payload: dict,
    mode: str,
    host: str,
) -> HookResult:
    """Block one stop when a managed checkout has unlinked commits."""
    lines = _brief_lines(store, cwd, commits)
    loose = [line.strip() for line in lines if line.strip().startswith("unlinked")]
    continued = bool(payload.get("stop_hook_active"))
    try:
        continued = continued or int(payload.get("loop_count") or 0) > 0
    except (TypeError, ValueError):
        continued = True
    if loose and mode == "strict" and host != "opencode" and not continued:
        scope = hook_scope.resolve(store, cwd)
        if scope.managed and scope.task is not None:
            task_id = scope.task.id
            parts = [f"lazyplan: {len(loose)} plan(s) have unlinked commits."]
            parts.append(f"Link them with `lpui link --kind task --id {task_id}`.")
            if session is not None:
                parts.append(
                    f"Then end S{session.id} with `lpui session end --id S{session.id} --summary`."
                )
            return HookResult(block=" ".join(parts))
    return HookResult(_stop_text(store, cwd, commits, session, loose=loose)).capped()


def _stop_text(
    store: InsightsPort,
    cwd: Path,
    commits: list[audit.Commit] | None,
    session: Session | None = None,
    loose: list[str] | None = None,
) -> str:
    lines = _brief_lines(store, cwd, commits)
    parts = (
        loose
        if loose is not None
        else [line.strip() for line in lines if line.strip().startswith("unlinked")]
    )
    tracked = session
    if tracked is None:
        rows = store.list_sessions(open_only=True, limit=1)
        tracked = rows[0] if rows else None
    if tracked is not None:
        state = session_services.session_state(tracked)
        parts.append(
            f"session S{tracked.id} is {state}; run `lpui session end --id S{tracked.id} --summary`"
        )
    if not parts:
        return ""
    return "lazyplan: " + "; ".join(parts)


def _next_handoff(store: InsightsPort) -> str:
    """First next task across active plans, as a session handoff."""
    payload = brief.build(store)
    for plan in payload.get("plans") or []:
        task = plan.get("next")
        if task:
            return f"next: T{task['id']} {task['title']}"[:2000]
    return ""


def session_end_result(store: AppPort, session: Session | None, host: str) -> HookResult:
    """Close an open session with an automatic summary and handoff."""
    if session is None or session.ended:
        return HookResult()
    scope = hook_scope.resolve(store, session.repo_path or None)
    task = scope.task if scope.managed else None
    if task is None and scope.managed:
        current = _doing_task(store)
        task = None if current is None else store.get_task(current)
    summary = f"ended by {host or 'agent'}"
    if task is not None:
        summary += f" while working T{task.id} {task.title}"
    handoff = session.handoff or _next_handoff(store)
    session_services.end_session(
        store,
        session.id,
        session.actor or "agent",
        summary=summary,
        handoff=handoff,
        auto=True,
    )
    return HookResult()


def _commit_reason() -> str:
    """Actionable denial text for a commit without a doing task."""
    return (
        "lazyplan: commit blocked; this checkout has no doing task. "
        "Run `lpui next` or `lpui task move --id ID --to doing`, then commit."
    )


def commit_result(store: AppPort, cwd: Path, command: str, mode: str) -> HookResult:
    """Deny a git commit when a managed checkout has no doing task."""
    if "git commit" not in command:
        return HookResult()
    scope = hook_scope.resolve(store, cwd)
    if not scope.managed or scope.task is not None:
        return HookResult()
    reason = _commit_reason()
    if mode == "strict":
        return HookResult(block=reason)
    return HookResult(reason, context=True).capped()


def post_tool_text(store: InsightsPort, command: str, path: str) -> str:
    """Reminder after a commit or an edit; empty for unrelated tools."""
    if "git commit" in command:
        task_id = _doing_task(store)
        if task_id is None:
            return "lazyplan: commit landed; start or pick a task with `lpui brief`."
        return f"lazyplan: commit landed; link it with `lpui link --kind task --id {task_id}`."
    if not path:
        return ""
    task_id = _doing_task(store)
    if task_id is None:
        return "lazyplan: edit landed; start or pick a task with `lpui brief`."
    patterns = store.list_touchpoints(task_id)
    if _matches_task(path, patterns):
        return (
            f"lazyplan: {path} belongs to T{task_id};"
            f" update the task or note the decision when the slice is done."
        )
    return f"lazyplan: edited {path}; if this changes the task scope, edit the plan first."
