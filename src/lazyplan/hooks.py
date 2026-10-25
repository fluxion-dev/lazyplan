"""Canonical hook events for coding-agent hosts.

One read-only entry point maps host lifecycle events to a short reminder.
Hooks never write to the database, never move a task, and always let the
agent continue. Host-specific output shaping lives in `hook_hosts`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from . import audit, brief
from .repo import resolve_db_path
from .store import Store

EVENTS = ("session-start", "prompt-submit", "post-tool", "stop", "pre-compact")
HOSTS = ("opencode", "claude", "gemini", "codex", "cursor")
NO_HOOKS_ENV = "LAZYPLAN_NO_HOOKS"
MAX_TEXT = 2000


@dataclass
class HookResult:
    """What a hook wants the host to show; empty text means stay quiet."""

    text: str = ""
    context: bool = False

    def capped(self) -> HookResult:
        """Keep injected context inside the host's patience."""
        return HookResult(self.text[:MAX_TEXT], self.context)


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


def _open_db() -> Store | None:
    """Existing database only; a hook never creates one."""
    path = Path(resolve_db_path()).expanduser()
    if not path.is_file():
        return None
    try:
        return Store(str(path))
    except (RuntimeError, OSError):
        return None


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


def _brief_lines(store: Store, cwd: Path, commits: list[audit.Commit] | None) -> list[str]:
    payload = brief.build(store, commits=commits, cwd=cwd)
    return brief.lines(payload)


def _doing_task(store: Store) -> int | None:
    for plan in store.list_plans():
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                if task.status.value == "doing":
                    return task.id
    return None


def _session_text(store: Store, cwd: Path, commits: list[audit.Commit] | None) -> str:
    payload = brief.build(store, commits=commits, cwd=cwd)
    if not payload.get("plans"):
        return ""
    return "\n".join(brief.lines(payload)).strip()


def _stop_text(store: Store, cwd: Path, commits: list[audit.Commit] | None) -> str:
    lines = _brief_lines(store, cwd, commits)
    loose = [line for line in lines if line.strip().startswith("unlinked")]
    if not loose:
        return ""
    return "lazyplan: " + "; ".join(line.strip() for line in loose)


def _post_tool_text(store: Store, payload: dict) -> str:
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
) -> HookResult:
    """Decide one event's reminder without touching host output formats."""
    if event not in EVENTS:
        return HookResult()
    store = _open_db()
    if store is None:
        return HookResult()
    here = cwd or Path.cwd()
    try:
        if event in ("session-start", "pre-compact"):
            return HookResult(_session_text(store, here, commits), context=True).capped()
        if event == "stop":
            return HookResult(_stop_text(store, here, commits)).capped()
        if event == "post-tool":
            return HookResult(_post_tool_text(store, payload)).capped()
    except (RuntimeError, OSError):
        return HookResult()
    return HookResult()


def run(
    event: str,
    payload: dict,
    host: str = "",
    cwd: Path | None = None,
    commits: list[audit.Commit] | None = None,
) -> HookResult:
    """Entry point used by the CLI; never raises and never blocks."""
    if os.environ.get(NO_HOOKS_ENV, "").strip():
        return HookResult()
    try:
        return build_result(event, payload, cwd, commits)
    except (RuntimeError, OSError, ValueError):
        return HookResult()
