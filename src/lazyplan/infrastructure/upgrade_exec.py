"""Run the pipx, uv, or venv install commands for one self-update.

The runners live here to keep ``upgrade.py`` inside its module budget. They
import ``upgrade`` lazily: ``upgrade`` re-exports these functions, so a
module-level import would be circular.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from . import update_log

UPGRADE_TIMEOUT = 300.0


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _command_log(
    kind: str,
    method: str,
    command: list[str],
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
) -> str:
    """Write one command log; return the log suffix for an error message."""
    try:
        path = update_log.record_update(
            kind,
            method=method,
            command=command,
            cwd=os.getcwd(),
            exe=sys.executable,
            returncode=returncode,
            stdout=_text(stdout),
            stderr=_text(stderr),
        )
    except OSError:
        return ""
    return f"; log: {path}"


def _run_install(method: str, cmds: list[list[str]], timeout: float) -> None:
    """Run each command until one succeeds; raise with the last log."""
    from .upgrade import UpgradeError

    last_lines: list[str] = []
    last_log = ""
    for cmd in cmds:
        try:
            out = subprocess.run(
                cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout
            )
        except OSError as exc:
            log = _command_log("upgrade", method, cmd, None, stderr=str(exc))
            raise UpgradeError(f"cannot run {' '.join(cmd)}: {exc}{log}") from exc
        last_log = _command_log(
            "upgrade",
            method,
            cmd,
            out.returncode,
            out.stdout or "",
            out.stderr or "",
        )
        if out.returncode == 0:
            return
        last_lines = (out.stderr or out.stdout or "").strip().splitlines()[:3]
    raise UpgradeError(f"{method} upgrade failed: {'; '.join(last_lines)}{last_log}")


def upgrade_pipx(
    version: str,
    timeout: float = UPGRADE_TIMEOUT,
    installed: str | None = None,
) -> None:
    """Mirror install.sh do_pipx: upgrade, falling back to a forced install."""
    from .upgrade import PIPX, PYPI_PKG, UpgradeError, require_newer

    require_newer(version, installed)
    if shutil.which("pipx") is None:
        raise UpgradeError("pipx is not on PATH")
    _run_install(
        PIPX,
        [
            ["pipx", "upgrade", PYPI_PKG, "--pip-args", f"=={version}"],
            ["pipx", "install", f"{PYPI_PKG}=={version}", "--force"],
        ],
        timeout,
    )


def upgrade_uv(
    version: str,
    timeout: float = UPGRADE_TIMEOUT,
    installed: str | None = None,
) -> None:
    """Reinstall the pinned uv tool, falling back to a plain upgrade."""
    from .upgrade import PYPI_PKG, UV, UpgradeError, require_newer

    require_newer(version, installed)
    if shutil.which("uv") is None:
        raise UpgradeError("uv is not on PATH")
    _run_install(
        UV,
        [
            ["uv", "tool", "install", f"{PYPI_PKG}=={version}", "--force"],
            ["uv", "tool", "upgrade", PYPI_PKG],
        ],
        timeout,
    )


def upgrade_venv(
    version: str,
    exe: str,
    timeout: float = UPGRADE_TIMEOUT,
    installed: str | None = None,
) -> None:
    """Reinstall the running venv from PyPI (the install.sh do_venv layout)."""
    from .upgrade import PYPI_PKG, VENV, require_newer

    require_newer(version, installed)
    _run_install(VENV, [[exe, "-m", "pip", "install", f"{PYPI_PKG}=={version}"]], timeout)
