"""Canonical hook events for coding-agent hosts.

One entry point maps host lifecycle events to a short reminder and keeps the
checkout's session heartbeat current. Hooks never move a task and always let
the agent continue. Host-specific output shaping lives in `hook_hosts`.
"""

from __future__ import annotations

import json
import os
import re
import select
import stat
import sys
import time
from pathlib import Path
from typing import TextIO, cast

from ..core.entities import HookResult, Session
from ..core.policies import hooks as hook_modes
from ..core.policies.sessions import phase_for_event
from ..core.ports.app import AppPort
from ..core.ports.insights import InsightsPort
from ..infrastructure.repo import git_common_dir
from . import attribution, audit, context, hook_policy
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
STDIN_TIMEOUT = 0.5


def _read_bounded(stream: TextIO, timeout: float = STDIN_TIMEOUT) -> str:
    """Read stdin without waiting for a pipe the host leaves open."""
    try:
        fd = stream.fileno()
    except (AttributeError, OSError, ValueError):
        # StringIO and other non-file streams already return immediately.
        return stream.read()
    if os.name == "nt":
        return _read_windows(fd, timeout)
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            wait = remaining if not chunks else 0.02
            if wait <= 0:
                break
            ready, _, _ = select.select([fd], [], [], wait)
            if not ready:
                break
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
    except (OSError, ValueError):
        return ""
    return b"".join(chunks).decode("utf-8", "replace")


def _read_windows(fd: int, timeout: float) -> str:
    """Poll a Windows pipe and read only the bytes already waiting in it.

    A blocking read left pending on stdin makes every child process that
    inherits the pipe, starting with git, hang at startup.
    """
    mode = os.fstat(fd).st_mode
    if not stat.S_ISFIFO(mode):
        return "" if stat.S_ISCHR(mode) else _read_to_end(fd).decode("utf-8", "replace")
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while True:
        waiting = _pipe_waiting(fd)
        if waiting is None:
            break
        if waiting:
            chunks.append(os.read(fd, waiting))
            deadline = time.monotonic() + 0.02
        elif time.monotonic() >= deadline:
            break
        else:
            time.sleep(0.005)
    return b"".join(chunks).decode("utf-8", "replace")


def _read_to_end(fd: int) -> bytes:
    chunks: list[bytes] = []
    while chunk := os.read(fd, 65536):
        chunks.append(chunk)
    return b"".join(chunks)


def _pipe_waiting(fd: int) -> int | None:
    """Bytes waiting in a Windows pipe; None once the writer has closed it."""
    if sys.platform != "win32":
        return None
    import ctypes
    import msvcrt
    from ctypes import wintypes

    available = wintypes.DWORD()
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
    peek = ctypes.windll.kernel32.PeekNamedPipe
    if not peek(handle, None, 0, None, ctypes.byref(available), None):
        return None
    return int(available.value)


def read_payload(stream: TextIO) -> dict:
    """Parse host JSON from stdin; malformed or empty input is an empty payload."""
    try:
        raw = _read_bounded(stream)
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


def _host_session(payload: dict) -> str:
    """The host's own session id from the common payload shapes."""
    for key in ("host_session", "session_id", "sessionID", "thread_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("sessionID", "session_id", "thread_id"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _project_key(repo: str) -> str:
    """Stable project key: the git common dir, else the checkout path."""
    common = git_common_dir(repo)
    return common or repo


def _track_session(
    store: AppPort,
    event: str,
    host: str,
    cwd: Path,
    payload: dict,
) -> Session | None:
    """Keep each host session's row heartbeat and phase in step with the host."""
    now = time.time()
    repo = store.checkout_path(str(cwd))
    project = _project_key(repo)
    host_session = _host_session(payload)
    branch = attribution.current_branch(repo)
    if event in ("session-start", "prompt-submit", "stop"):
        session_services.reap_idle_sessions(store, now=now, repo_path=repo)
    if host_session:
        session = store.session_for_host(host, host_session, project)
    else:
        session = store.open_session_for(repo, host=host)
    if session is None:
        if event == "session-end":
            return None
        if not host_session and event in ("pre-tool", "post-tool", "pre-compact"):
            return None
        resolved = attribution.resolve(store, repo, branch)
        result = session_services.start_session(
            store,
            host or "agent",
            plan_id=resolved.plan_id,
            repo_path=repo,
            branch=branch,
            host=host,
            host_session=host_session,
            phase=phase_for_event(event),
        )
        session = cast(Session, result["session"])
    elif event == "session-end":
        if not host_session:
            return session
        detached, last = store.detach_host_binding(host, host_session, project)
        return detached if last else None
    else:
        session = _refresh_tracking(store, session, event, host, repo, branch)
    if session is not None and host_session:
        store.bind_session(host, host_session, project, repo, session.id, now=now)
    return session


def _refresh_tracking(
    store: AppPort,
    session: Session,
    event: str,
    host: str,
    repo: str,
    branch: str,
) -> Session | None:
    """Heartbeat one row and re-resolve attribution while it stays automatic."""
    replace_plan = session.plan_source != "manual"
    plan_id = attribution.resolve(store, repo, branch).plan_id if replace_plan else None
    phase = phase_for_event(event) if event in ("session-start", "prompt-submit", "stop") else None
    return session_services.touch_session(
        store,
        session.id,
        phase=phase,
        host=host,
        branch=branch,
        plan_id=plan_id,
        replace_plan=replace_plan,
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
        session = _track_session(store, event, who, here, payload)
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
            text = hook_policy.post_tool_text(store, here, _command(payload), _file_path(payload))
            return HookResult(text, context=True).capped()
    except (RuntimeError, OSError, ValueError, KeyError):
        return HookResult()
    return HookResult()


def probe(store: AppPort | None, cwd: Path | None = None) -> dict:
    """Read-only hook readiness report; never creates a database or a row."""
    started = time.perf_counter()
    if store is None:
        return {
            "ok": False,
            "db": None,
            "session": None,
            "reason": "no database",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    try:
        repo = store.checkout_path(str(cwd or Path.cwd()))
        session = store.open_session_for(repo)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "db": store.db_path,
            "session": None,
            "reason": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    return {
        "ok": True,
        "db": store.db_path,
        "session": session.id if session is not None else None,
        "reason": "",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


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
