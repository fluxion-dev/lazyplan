"""Detect how `lpui` was installed and upgrade user-space installs. Stdlib only."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = "fluxion-dev/lazyplan"
PYPI_PKG = "lazyplan-tui"
RELEASES_LATEST = f"https://github.com/{REPO}/releases/latest"
RESOLVE_TIMEOUT = 10.0
UPGRADE_TIMEOUT = 300.0

PIPX = "pipx"
VENV = "venv"
RPM = "rpm"
DEB = "deb"
SOURCE = "source"
UNKNOWN = "unknown"

UPGRADEABLE = {PIPX, VENV}


class UpgradeError(Exception):
    """The latest version could not be resolved, or the upgrade itself failed."""


@dataclass
class InstallInfo:
    method: str
    upgradeable: bool
    detail: str = ""


def _exe_parts(exe: str) -> list[str]:
    return Path(exe).as_posix().split("/")


def _looks_like_pipx(exe: str) -> str | None:
    """The pipx venv dir for this package, else None."""
    parts = _exe_parts(exe)
    if "pipx" in parts and "venvs" in parts and PYPI_PKG in parts:
        try:
            idx = parts.index(PYPI_PKG)
        except ValueError:
            return None
        return "/" + "/".join(parts[1 : idx + 1])
    return None


def _in_venv(prefix: str, base_prefix: str) -> bool:
    return os.path.normpath(prefix) != os.path.normpath(base_prefix)


def _dist_direct_url() -> str | None:
    """Raw direct_url.json for the installed dist, else None (not pip-installed)."""
    try:
        from importlib.metadata import distribution
    except ImportError:  # pragma: no cover - python >=3.11 always has it
        return None
    try:
        dist = distribution(PYPI_PKG)
    except Exception:
        return None
    try:
        text = dist.read_text("direct_url.json")
    except Exception:
        return None
    return text


def _is_editable_install() -> bool:
    text = _dist_direct_url()
    if text is None:
        return False
    return '"editable":true' in text.replace(" ", "")


def _probe(cmd: list[str]) -> bool:
    if shutil.which(cmd[0]) is None:
        return False
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=10)
    except OSError:
        return False
    return out.returncode == 0


def _looks_like_source(exe: str, cwd: str) -> bool:
    """A checkout of this repo (pyproject naming lazyplan-tui) near exe or cwd."""
    for start in (str(Path(exe).parent), cwd):
        here = Path(start)
        for _ in range(6):
            marker = here / "pyproject.toml"
            try:
                text = marker.read_text()
            except OSError:
                pass
            else:
                if 'name = "lazyplan-tui"' in text:
                    return True
            parent = here.parent
            if parent == here:
                break
            here = parent
    return False


def detect(
    exe: str | None = None,
    prefix: str | None = None,
    base_prefix: str | None = None,
    cwd: str | None = None,
) -> InstallInfo:
    """Classify this install; mirrors the install.sh method probes."""
    exe = exe if exe is not None else sys.executable
    prefix = prefix if prefix is not None else sys.prefix
    base_prefix = base_prefix if base_prefix is not None else sys.base_prefix
    cwd = cwd if cwd is not None else os.getcwd()

    pipx_dir = _looks_like_pipx(exe)
    if pipx_dir is not None:
        return InstallInfo(PIPX, True, pipx_dir)
    if _in_venv(prefix, base_prefix):
        if _is_editable_install() or _looks_like_source(exe, cwd):
            return InstallInfo(SOURCE, False, "editable or source checkout; pull git instead")
        return InstallInfo(VENV, True, prefix)
    if _probe(["rpm", "-q", "lazyplan"]):
        return InstallInfo(RPM, False, "system rpm install")
    if _probe(["dpkg", "-s", "lazyplan"]):
        return InstallInfo(DEB, False, "system deb install")
    if _looks_like_source(exe, cwd):
        return InstallInfo(SOURCE, False, "source checkout; pull git instead")
    return InstallInfo(UNKNOWN, False, "unrecognized layout; reinstall via install.sh")


def parse_version(text: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not m:
        raise UpgradeError(f"cannot parse a version from {text!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def version_text(version: tuple[int, int, int]) -> str:
    return ".".join(str(n) for n in version)


def latest_version(timeout: float = RESOLVE_TIMEOUT) -> str:
    """Latest release version from the GitHub /releases/latest redirect."""
    req = urllib.request.Request(RELEASES_LATEST, headers={"User-Agent": "lpui-upgrade"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            final_url = resp.geturl()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpgradeError(f"cannot reach {RELEASES_LATEST}: {exc}") from exc
    tag = final_url.rstrip("/").rsplit("/", 1)[-1]
    if tag.startswith("v"):
        tag = tag[1:]
    try:
        parsed = parse_version(tag)
    except UpgradeError as exc:
        raise UpgradeError(f"cannot parse latest version from {final_url!r}") from exc
    return version_text(parsed)


INSTALL_SH = (
    "curl -fsSL https://github.com/fluxion-dev/lazyplan/releases/latest/download/install.sh | sh"
)


def guard_message(info: InstallInfo) -> str:
    """Why this install cannot self-upgrade, and what to run instead."""
    upgradeable = "`lpui upgrade` only manages pipx and venv installs"
    if info.method == RPM:
        return (
            f"system rpm install: upgrade with your package manager "
            f"(e.g. `sudo dnf upgrade lazyplan`); {upgradeable}"
        )
    if info.method == DEB:
        return (
            "system deb install: run `sudo apt update && "
            f"sudo apt install --only-upgrade lazyplan`; {upgradeable}"
        )
    if info.method == SOURCE:
        return f"source checkout ({info.detail}): update with `git pull`; {upgradeable}"
    return f"unrecognized install layout ({info.detail}); reinstall with {INSTALL_SH}"


def run_upgrade(info: InstallInfo, version: str, exe: str | None = None) -> None:
    """Dispatch to the per-method runner; UPGRADEABLE is the source of truth."""
    if info.method not in UPGRADEABLE:
        raise UpgradeError(f"no upgrade path for a {info.method} install")
    if info.method == PIPX:
        upgrade_pipx(version)
    else:
        upgrade_venv(version, exe or sys.executable)


def upgrade_pipx(version: str, timeout: float = UPGRADE_TIMEOUT) -> None:
    """Mirror install.sh do_pipx: upgrade, falling back to a forced install."""
    if shutil.which("pipx") is None:
        raise UpgradeError("pipx is not on PATH")
    cmds = [
        ["pipx", "upgrade", PYPI_PKG, "--pip-args", f"=={version}"],
        ["pipx", "install", f"{PYPI_PKG}=={version}", "--force"],
    ]
    last_lines: list[str] = []
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except OSError as exc:
            raise UpgradeError(f"cannot run {' '.join(cmd)}: {exc}") from exc
        if out.returncode == 0:
            return
        last_lines = (out.stderr or out.stdout or "").strip().splitlines()[:3]
    raise UpgradeError(f"pipx upgrade failed: {'; '.join(last_lines)}")


def upgrade_venv(version: str, exe: str, timeout: float = UPGRADE_TIMEOUT) -> None:
    """Reinstall the running venv from PyPI (the install.sh do_venv layout)."""
    pip = str(Path(exe).parent / "pip")
    if not Path(pip).exists():
        pip = str(Path(exe).parent / "pip3")
    cmd = [pip, "install", f"{PYPI_PKG}=={version}"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except OSError as exc:
        raise UpgradeError(f"cannot run {' '.join(cmd)}: {exc}") from exc
    if out.returncode != 0:
        detail = "; ".join((out.stderr or out.stdout or "").strip().splitlines()[:3])
        raise UpgradeError(f"venv reinstall failed: {detail}")
