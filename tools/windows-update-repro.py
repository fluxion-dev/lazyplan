#!/usr/bin/env python3
"""Reproduce a Windows self-update in isolated homes.

Installs a pinned prior release with pipx, stages a locally built 9.9.9 wheel
in a temporary lazyplan home, then runs the installed version's
apply_on_launch path in a child process and prints the result.

Usage:
  python tools/windows-update-repro.py [--prior-version 0.31.0]
                                       [--python PYTHON] [--pipx PATH]
                                       [--keep DIR]

The script never touches the real pipx or lazyplan homes. Run it on Windows
to capture the failing command and log from the current release.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "lazyplan-tui"
TEST_VERSION = "9.9.9"
TEST_URL = "https://files.pythonhosted.org/packages/local/test.whl"


def log(message: str) -> None:
    print(message, flush=True)


def run(
    command: list[str],
    *,
    env: dict[str, str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    log("$ " + subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout.strip():
        log(result.stdout.rstrip())
    if result.stderr.strip():
        log(result.stderr.rstrip())
    if check and result.returncode != 0:
        raise SystemExit(f"command failed ({result.returncode}): {command[0]}")
    return result


def build_wheel(python: str, destination: Path, version: str = TEST_VERSION) -> Path:
    """Build the current committed tree at *version*."""
    log("$ git archive HEAD")
    archive = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"],
        capture_output=True,
        check=True,
    )
    source = destination / "source"
    source.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(source)
    pyproject = source / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(
        r'^version = ".*"$',
        f'version = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    pyproject.write_text(text, encoding="utf-8")
    wheels = destination / "wheels"
    wheels.mkdir()
    run(
        [python, "-m", "pip", "wheel", str(source), "--no-deps", "--wheel-dir", str(wheels)],
        env=dict(os.environ),
        check=True,
    )
    return next(wheels.glob("*.whl"))


def isolated_env(root: Path, pipx: str) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(root / "home")
    env["USERPROFILE"] = str(root / "home")
    env["LOCALAPPDATA"] = str(root / "localappdata")
    env["PIPX_HOME"] = str(root / "pipx-home")
    env["PIPX_BIN_DIR"] = str(root / "pipx-bin")
    env["PIPX_DEFAULT_PYTHON"] = sys.executable
    env["PATH"] = os.pathsep.join([str(root / "pipx-bin"), env.get("PATH", "")])
    env["PIPX"] = pipx
    for key in ("HOME", "USERPROFILE", "LOCALAPPDATA"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def shared_home(env: dict[str, str]) -> Path:
    if os.name == "nt":
        base = Path(env["LOCALAPPDATA"]) / "lazyplan"
    else:
        base = Path(env["HOME"]) / ".lazyplan"
    return base


def stage_wheel(env: dict[str, str], wheel: Path, version: str = TEST_VERSION) -> Path:
    update_dir = shared_home(env) / "updates"
    update_dir.mkdir(parents=True, exist_ok=True)
    target = update_dir / wheel.name
    shutil.copy2(wheel, target)
    raw = target.read_bytes()
    payload = {
        "schema": 1,
        "version": version,
        "method": "pipx",
        "filename": target.name,
        "url": TEST_URL,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
        "staged_at": 1_700_000_000.0,
    }
    (update_dir / "staged.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return update_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prior-version", default="0.31.0")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--pipx", default=shutil.which("pipx") or "")
    parser.add_argument("--keep", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.pipx:
        print("pipx is required on PATH; install it or pass --pipx PATH", file=sys.stderr)
        return 2
    root = Path(tempfile.mkdtemp(prefix="lazyplan-update-repro-"))
    try:
        env = isolated_env(root, args.pipx)
        wheel = build_wheel(args.python, root)
        log(f"built test wheel: {wheel}")
        run(
            [
                args.pipx,
                "install",
                "--backend",
                "pip",
                f"{PACKAGE}=={args.prior_version}",
            ],
            env=env,
        )
        venv = Path(env["PIPX_HOME"]) / "venvs" / PACKAGE
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise SystemExit(f"cannot find the pipx venv python: {python}")
        update_dir = stage_wheel(env, wheel)
        log(f"staged wheel: {update_dir / wheel.name}")
        code = (
            "from lazyplan.infrastructure.update_stage import apply_on_launch\n"
            "from lazyplan.presentation.cli.parser import package_version\n"
            "print(apply_on_launch(package_version()))\n"
        )
        result = run([str(python), "-c", code], env=env, check=False)
        log(f"apply exit: {result.returncode}")
        version = run(
            [
                str(python),
                "-c",
                ("from importlib.metadata import version; print(version('lazyplan-tui'))"),
            ],
            env=env,
            check=False,
        )
        log(f"installed after apply: {version.stdout.strip() or '<unknown>'}")
        log(f"logs: {shared_home(env) / 'logs'}")
        return 0 if TEST_VERSION in version.stdout else 1
    finally:
        if args.keep is None:
            shutil.rmtree(root, ignore_errors=True)
        else:
            log(f"kept workspace: {root}")


if __name__ == "__main__":
    raise SystemExit(main())
