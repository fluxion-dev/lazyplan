"""Canonical hook events for coding-agent hosts.

One entry point maps host lifecycle events to a short reminder and keeps the
checkout's session heartbeat current. Hooks never move a task and always let
the agent continue. Host-specific output shaping lives in `hook_hosts`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import TextIO, cast

from ..core.entities import HookResult, Session
from ..core.policies import hooks as hook_modes
from ..core.policies.sessions import IDLE_AFTER_SECS, phase_for_event
from ..core.ports.app import AppPort
from ..core.ports.insights import InsightsPort
from . import audit, context, hook_policy
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
NO_HOOKS_ENV = hook_modes.NO_HOOKS_ENV


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


_PATCH_FILE = re.compile(r"^\*\*\* (?:Update|Add) File: (.+)$", re.MULTILINE)


def _file_path(payload: dict) -> str:
    """Edited file path, including the path inside an apply_patch body."""
    for key in ("tool_input", "arguments"):
        value = payload.get(key)
        if isinstance(value, dict):
            for name in ("file_path", "path", "filename"):
                path = value.get(name)
                if isinstance(path, str) and path.strip():
                    return path.strip()
    for name in ("file_path", "path"):
        path = payload.get(name)
        if isinstance(path, str) and path.strip():
            return path.strip()
    match = _PATCH_FILE.search(_command(payload))
    return match.group(1).strip() if match else ""


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


def _prompt_text(store: InsightsPort) -> str:
    """Small active-plan packet for every user prompt."""
    payload = context.build(store, max_chars=1200)
    if not payload.get("plans"):
        return ""
    return "\n".join(context.lines(payload)).strip()[:1200]


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
            return hook_policy.stop_result(store, here, commits, session, payload, mode, who)
        if event == "session-end":
            return hook_policy.session_end_result(store, session, who)
        if event == "prompt-submit":
            return HookResult(_prompt_text(store), context=True).capped()
        if event == "pre-tool":
            return hook_policy.commit_result(store, here, _command(payload), mode)
        if event == "post-tool":
            text = hook_policy.post_tool_text(store, _command(payload), _file_path(payload))
            return HookResult(text).capped()
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
    requested = hook_modes.mode_from_env(os.environ)
    if requested == "off":
        return HookResult()
    effective = requested or hook_modes.normalize_mode(mode)
    try:
        return build_result(event, payload, cwd, commits, host, store, effective)
    except (RuntimeError, OSError, ValueError):
        return HookResult()
