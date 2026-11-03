"""Full update logs: one file per install attempt, under the shared home."""

from __future__ import annotations

import os
import re
import shlex
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from . import textfile
from .repo import shared_home

LOG_DIR = "logs"


def logs_dir(home: str | Path | None = None) -> Path:
    """Directory that holds update logs."""
    return shared_home(home) / LOG_DIR


def _label(kind: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", kind).strip("-")
    return safe or "update"


def log_path(
    kind: str,
    home: str | Path | None = None,
    now: float | None = None,
    pid: int | None = None,
) -> Path:
    """Return the deterministic log path for one update attempt."""
    stamp = int(time.time() if now is None else now)
    process = os.getpid() if pid is None else pid
    return logs_dir(home) / f"update-{_label(kind)}-{stamp}-{process}.log"


def record_update(
    kind: str,
    *,
    method: str,
    command: Sequence[str],
    cwd: str | Path,
    exe: str,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    extra: Mapping[str, object] | None = None,
    home: str | Path | None = None,
    now: float | None = None,
    pid: int | None = None,
    path: Path | None = None,
) -> Path:
    """Write one update attempt and return its log path."""
    target = path or log_path(kind, home, now, pid)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"method: {method}",
        f"exe: {exe}",
        f"cwd: {cwd}",
        f"command: {shlex.join([str(part) for part in command])}",
        f"returncode: {returncode}",
    ]
    for key, value in (extra or {}).items():
        lines.append(f"{key}: {value}")
    lines.extend(["", "stdout:", stdout.rstrip(), "", "stderr:", stderr.rstrip(), ""])
    textfile.write(target, "\n".join(lines))
    return target
