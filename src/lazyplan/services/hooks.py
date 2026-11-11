"""Canonical hook events for coding-agent hosts.

One entry point maps host lifecycle events to a short reminder and keeps the
checkout's session heartbeat current. Hooks never move a task and always let
the agent continue. Host-specific output shaping lives in `hook_hosts`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TextIO, cast

from ..core.entities import HookResult, Session
from ..core.policies import hooks as hook_policy
from ..core.policies.sessions import IDLE_AFTER_SECS, phase_for_event
from ..core.ports.app import AppPort
from ..core.ports.insights import InsightsPort
from . import audit, brief, context, hook_scope
from . import sessions as session_services

EVENTS = (
    "session-start",
    "prompt-submit",
    "pre-tool",
    "post-tool",
    "stop",
    "session-end",
    "pre-compact",
)
HOSTS = ("opencode", "claude", "gemini", "codex", "cursor")
NO_HOOKS_ENV = hook_policy.NO_HOOKS_ENV


def read_payload(stream: TextIO) -> dict:
    """Parse host JSON from stdin; malformed or empty input is an empty payload."""
    try:
        raw = stream.read()
    except (OSError, ValueError):
        return {}
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def detect_host(payload: dict, explicit: str = "") -> str:
    """Explicit --host wins; otherwise infer from known payload fields."""
    wanted = (explicit or "").strip().lower()
    if wanted in HOSTS:
        return wanted
    if "hook_event_name" in payload or "hookEventName" in payload:
        return "claude"
    if "workspace_roots" in payload or "cursor_version" in payload:
        return "cursor"
    if "thread_id" in payload or "turn_id" in payload:
        return "codex"
    if "session_id" in payload and "source" in payload:
        return "gemini"
    return "opencode"


def _command(payload: dict) -> str:
    """Bash command text from the common host payload shapes."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        text = tool_input.get("command")
        if isinstance(text, str):
            return text
    arguments = payload.get("arguments")
    if isinstance(arguments, dict):
        text = arguments.get("command")
        if isinstance(text, str):
            return text
    command = payload.get("command")
    return command if isinstance(command, str) else ""


def _brief_lines(store: InsightsPort, cwd: Path, commits: list[audit.Commit] | None) -> list[str]:
    payload = brief.build(store, commits=commits, cwd=cwd)
    return brief.lines(payload)


def _doing_task(store: InsightsPort) -> int | None:
    for plan in store.list_plans():
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                if task.status.value == "doing":
                    return task.id
    return None


def _doing_plan(store: InsightsPort) -> int | None:
    """The one plan with doing work, or None when it is ambiguous."""
    plans = {
        plan.id
        for plan in store.list_plans()
        for milestone in store.list_milestones(plan.id)
        for task in store.list_tasks(milestone.id)
        if task.status.value == "doing"
    }
    return plans.pop() if len(plans) == 1 else None


def _track_session(store: AppPort, event: str, host: str, cwd: Path) -> Session | None:
    """Keep the checkout's session heartbeat and phase in step with the host."""
    now = time.time()
    repo = store.checkout_path(str(cwd))
    if event in ("session-start", "prompt-submit", "stop"):
        session_services.reap_idle_sessions(
            store, now=now, idle_after=IDLE_AFTER_SECS, repo_path=repo
        )
    session = session_services.open_session_for(store, repo, host=host)
    if session is None:
        if event in ("pre-tool", "post-tool", "session-end", "pre-compact"):
            return None
        result = session_services.start_session(
            store,
            host or "agent",
            plan_id=_doing_plan(store),
            repo_path=repo,
            host=host,
            phase=phase_for_event(event),
        )
        return cast(Session, result["session"])
    if event in ("pre-tool", "post-tool", "session-end", "pre-compact"):
        return session_services.touch_session(store, session.id, host=host)
    return session_services.touch_session(
        store, session.id, phase=phase_for_event(event), host=host
    )


def _session_text(
    store: InsightsPort,
    cwd: Path,
    commits: list[audit.Commit] | None,
    session: Session | None = None,
) -> str:
    del cwd, commits
    payload = context.build(store, max_chars=2000)
    if not payload.get("plans"):
        return ""
    text = "\n".join(context.lines(payload)).strip()
    tracked = session
    if tracked is None:
        rows = store.list_sessions(open_only=True, limit=1)
        tracked = rows[0] if rows else None
    if tracked is not None:
        state = session_services.session_state(tracked)
        text += (
            f"\nsession    S{tracked.id} {state} @{tracked.actor};"
            f" end it with `lpui session end --id S{tracked.id} --summary`"
        )
    else:
        text += "\nsession    none open; start one with `lpui session start --plan P`"
    return text


def _stop_result(
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


def _prompt_text(store: InsightsPort) -> str:
    """Small active-plan packet for every user prompt."""
    payload = context.build(store, max_chars=1200)
    if not payload.get("plans"):
        return ""
    return "\n".join(context.lines(payload)).strip()[:1200]


def _commit_reason() -> str:
    """Actionable denial text for a commit without a doing task."""
    return (
        "lazyplan: commit blocked; this checkout has no doing task. "
        "Run `lpui next` or `lpui task move --id ID --to doing`, then commit."
    )


def _pre_tool_result(store: AppPort, cwd: Path, payload: dict, mode: str) -> HookResult:
    """Deny a git commit when a managed checkout has no doing task."""
    command = _command(payload)
    if "git commit" not in command:
        return HookResult()
    scope = hook_scope.resolve(store, cwd)
    if not scope.managed or scope.task is not None:
        return HookResult()
    reason = _commit_reason()
    if mode == "strict":
        return HookResult(block=reason)
    return HookResult(reason, context=True).capped()


def _post_tool_text(store: InsightsPort, payload: dict) -> str:
    command = _command(payload)
    if "git commit" not in command:
        return ""
    task_id = _doing_task(store)
    if task_id is None:
        return "lazyplan: commit landed; start or pick a task with `lpui brief`."
    return f"lazyplan: commit landed; link it with `lpui link --kind task --id {task_id}`."


def build_result(
    event: str,
    payload: dict,
    cwd: Path | None = None,
    commits: list[audit.Commit] | None = None,
    host: str = "",
    store: AppPort | None = None,
    mode: str = "strict",
) -> HookResult:
    """Decide one event's reminder without touching host output formats."""
    if event not in EVENTS:
        return HookResult()
    if store is None:
        return HookResult()
    here = cwd or Path.cwd()
    who = host or detect_host(payload)
    try:
        session = _track_session(store, event, who, here)
        if event in ("session-start", "pre-compact"):
            return HookResult(_session_text(store, here, commits, session), context=True).capped()
        if event == "stop":
            return _stop_result(store, here, commits, session, payload, mode, who)
        if event == "prompt-submit":
            return HookResult(_prompt_text(store), context=True).capped()
        if event == "pre-tool":
            return _pre_tool_result(store, here, payload, mode)
        if event == "post-tool":
            return HookResult(_post_tool_text(store, payload)).capped()
    except (RuntimeError, OSError, ValueError, KeyError):
        return HookResult()
    return HookResult()


def run(
    event: str,
    payload: dict,
    host: str = "",
    cwd: Path | None = None,
    commits: list[audit.Commit] | None = None,
    store: AppPort | None = None,
    mode: str = "strict",
) -> HookResult:
    """Entry point used by the CLI; never raises and never blocks."""
    requested = hook_policy.mode_from_env(os.environ)
    if requested == "off":
        return HookResult()
    effective = requested or hook_policy.normalize_mode(mode)
    try:
        return build_result(event, payload, cwd, commits, host, store, effective)
    except (RuntimeError, OSError, ValueError):
        return HookResult()
