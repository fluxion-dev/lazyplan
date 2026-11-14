"""Canonical hook events for coding-agent hosts.

One entry point maps host lifecycle events to a short reminder and applies
them to the exact agent registry row. Hooks never move a task and always let
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
from typing import TextIO

from ..core.entities import HookResult
from ..core.policies import hooks as hook_modes
from ..core.ports.app import AppPort
from ..core.ports.insights import InsightsPort
from ..infrastructure.repo import shared_git_lookups
from . import audit, context, coordination, hook_policy

EVENTS = hook_modes.EVENTS
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


def _agent_text(store: AppPort, cwd: Path, commits: list[audit.Commit] | None) -> str:
    """Session-start packet: the active plan and this checkout's claims."""
    del commits
    payload = context.build(store, max_chars=2000)
    if not payload.get("plans"):
        return ""
    text = "\n".join(context.lines(payload)).strip()
    held = coordination.checkout_claims(store, store.checkout_path(str(cwd)))
    if held:
        names = ", ".join(f"T{claim['task_id']} @{claim['actor']}" for claim in held)
        text += f"\nclaims     {names}"
    else:
        text += "\nclaims     none here; take work with `lpui next` or move a task to doing"
    return text


def _compaction_text(store: AppPort, cwd: Path) -> str:
    """Summary guidance that carries the active plan through a compaction."""
    packet = _agent_text(store, cwd, None)
    if not packet:
        return ""
    return (
        "Keep this lazyplan state in the summary, with plan and task ids, "
        "so work resumes on the same task:\n" + packet
    )


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
        with shared_git_lookups():
            return _dispatch(store, event, payload, here, commits, who, mode)
    except (RuntimeError, OSError, ValueError, KeyError):
        return HookResult()


def _dispatch(
    store: AppPort,
    event: str,
    payload: dict,
    here: Path,
    commits: list[audit.Commit] | None,
    who: str,
    mode: str,
) -> HookResult:
    checkout = store.checkout_path(str(here))
    if event == "session-end":
        coordination.end_checkout_claims(store, checkout)
        return HookResult()
    coordination.renew_checkout_claims(store, checkout)
    if event == "session-start":
        return HookResult(_agent_text(store, here, commits), context=True).capped()
    if event == "pre-compact":
        return HookResult(_compaction_text(store, here), context=True).capped()
    if event == "stop":
        return hook_policy.stop_result(store, here, commits, payload, mode, who)
    if event == "prompt-submit":
        return HookResult(_prompt_text(store), context=True).capped()
    if event == "pre-tool":
        return hook_policy.commit_result(store, here, _command(payload), mode)
    if event == "post-tool":
        text = hook_policy.post_tool_text(store, here, _command(payload), _file_path(payload))
        return HookResult(text, context=True).capped()
    return HookResult()


def probe(store: AppPort | None, cwd: Path | None = None) -> dict:
    """Read-only hook readiness report; never creates a database or a row."""
    started = time.perf_counter()

    def report(ok: bool, db: str | None, claims: list[int], reason: str) -> dict:
        return {
            "ok": ok,
            "db": db,
            "claims": claims,
            "reason": reason,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    if store is None:
        return report(False, None, [], "no database")
    try:
        repo = store.checkout_path(str(cwd or Path.cwd()))
        held = [int(claim["task_id"]) for claim in coordination.checkout_claims(store, repo)]
    except (OSError, RuntimeError, ValueError) as exc:
        return report(False, store.db_path, [], str(exc))
    return report(True, store.db_path, held, "")


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
