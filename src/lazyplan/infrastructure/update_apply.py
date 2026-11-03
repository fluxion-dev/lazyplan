"""The Windows apply plan: what runs, where, and how lpui restarts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import update_log
from .update_stage import StagedUpdate, StageError, wheel_path
from .upgrade import PIPX, VENV, InstallInfo, detect

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ApplyPlan:
    """Everything the detached helper needs for one install attempt."""

    wheel: Path
    method: str
    python: str
    pipx: str
    command: tuple[str, ...]
    restart: tuple[str, ...]
    scripts: Path
    log_path: Path
    home: Path | None
    windows: bool


def _pipx_python(info: InstallInfo, windows: bool) -> str:
    if not info.detail:
        return sys.executable
    venv = Path(info.detail)
    return str(venv / ("Scripts/python.exe" if windows else "bin/python"))


def _restart_command(
    *,
    python: str,
    scripts: Path,
    argv: tuple[str, ...],
    use_path: bool,
) -> tuple[str, ...]:
    launcher = None
    if use_path:
        launcher = shutil.which("lpui") or shutil.which("lazyplan")
    if launcher:
        return (launcher, *argv)
    for name in ("lpui.exe", "lpui"):
        candidate = scripts / name
        if candidate.is_file():
            return (str(candidate), *argv)
    return (python, "-m", "lazyplan", *argv)


def build_apply_plan(
    update: StagedUpdate,
    *,
    home: str | Path | None = None,
    exe: str | None = None,
    info: InstallInfo | None = None,
    argv: tuple[str, ...] = (),
    windows: bool | None = None,
    restart: bool = True,
    now: float | None = None,
    pid: int | None = None,
) -> ApplyPlan:
    """Build the pipx/venv command and detached-helper metadata."""
    is_windows = os.name == "nt" if windows is None else windows
    install = info or detect(exe=exe)
    executable = exe or sys.executable
    wheel = wheel_path(update, home)
    pipx = shutil.which("pipx") or ""
    command: tuple[str, ...]
    if update.method == PIPX:
        if not pipx:
            raise StageError("pipx is not on PATH")
        python = _pipx_python(install, is_windows)
        scripts = Path(pipx).parent
        if is_windows:
            command = (pipx, "install", "--backend", "pip", str(wheel), "--force")
        else:
            command = (pipx, "install", str(wheel), "--force")
    elif update.method == VENV:
        python = executable
        scripts = Path(python).parent
        command = (python, "-m", "pip", "install")
        if is_windows:
            command += ("--no-input",)
        command += (str(wheel),)
    else:
        raise StageError(f"no apply path for a {update.method} install")
    restart_command = (
        _restart_command(
            python=python,
            scripts=scripts,
            argv=argv,
            use_path=update.method == PIPX,
        )
        if restart
        else ()
    )
    log = update_log.log_path("apply", home, now, pid)
    return ApplyPlan(
        wheel=wheel,
        method=update.method,
        python=python,
        pipx=pipx,
        command=command,
        restart=restart_command,
        scripts=scripts,
        log_path=log,
        home=Path(home) if home is not None else None,
        windows=is_windows,
    )


def _plan_payload(plan: ApplyPlan) -> dict[str, Any]:
    return {
        "wheel": str(plan.wheel),
        "method": plan.method,
        "python": plan.python,
        "pipx": plan.pipx,
        "command": list(plan.command),
        "restart": list(plan.restart),
        "scripts": str(plan.scripts),
        "log": str(plan.log_path),
        "home": str(plan.home) if plan.home is not None else None,
        "windows": plan.windows,
    }


def helper_command(plan: ApplyPlan, parent_pid: int) -> list[str]:
    """The detached helper invocation for one plan."""
    return [
        plan.python,
        "-m",
        "lazyplan._update_helper",
        "--parent-pid",
        str(parent_pid),
        "--plan-json",
        json.dumps(_plan_payload(plan), sort_keys=True),
    ]


def spawn_windows_apply(plan: ApplyPlan, parent_pid: int | None = None) -> Path:
    """Start the detached helper and return the path it will log to."""
    pid = os.getpid() if parent_pid is None else parent_pid
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    subprocess.Popen(
        helper_command(plan, pid),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=flags,
    )
    return plan.log_path


def _parent_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.WaitForSingleObject(handle, 0) == 0x102)
    finally:
        kernel32.CloseHandle(handle)


def wait_for_parent(
    pid: int,
    timeout: float = 60.0,
    poll: float = 0.1,
    alive: Callable[[int], bool] | None = None,
) -> bool:
    """Wait until *pid* exits; return False when the timeout expires."""
    is_alive = _parent_alive if alive is None else alive
    deadline = time.monotonic() + timeout
    while True:
        if not is_alive(pid):
            return True
        if time.monotonic() >= deadline:
            return False
        if poll > 0:
            time.sleep(poll)
