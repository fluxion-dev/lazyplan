#!/usr/bin/env python3
"""Real Windows smoke for the detached update path.

Builds two local wheels from HEAD (9.9.8 and 9.9.9), installs 9.9.8 into an
isolated pipx home, stages 9.9.9, and runs the installed apply_on_launch path
with restart disabled. The detached helper must update the venv after the
parent exits, with no package index reachable.

Then stages a corrupt wheel and proves the install fails, the failure is
parked with a log, and 9.9.8 still runs.

Usage:
  python tools/windows-update-smoke.py [--python PYTHON] [--pipx PATH]
                                      [--artifacts DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "lazyplan-tui"
PRIOR = "9.9.8"
TARGET = "9.9.9"
BAD = "9.9.10"
TIMEOUT = 120.0


def load_repro():
    path = ROOT / "tools" / "windows-update-repro.py"
    spec = importlib.util.spec_from_file_location("windows_update_repro", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["windows_update_repro"] = module
    spec.loader.exec_module(module)
    return module


def installed_version(repro, python: Path, env: dict[str, str]) -> str:
    result = repro.run(
        [
            str(python),
            "-c",
            "from importlib.metadata import version; print(version('lazyplan-tui'))",
        ],
        env=env,
        check=False,
    )
    return result.stdout.strip()


def wait_for(repro, predicate, label: str) -> None:
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {label}")


def apply_child(repro, python: Path, env: dict[str, str]) -> None:
    code = (
        "from lazyplan.infrastructure.update_stage import apply_on_launch\n"
        "from lazyplan.presentation.cli.parser import package_version\n"
        "print(apply_on_launch(package_version(), windows=True, restart=False))\n"
    )
    repro.run([str(python), "-c", code], env=env, check=False)


def copy_artifacts(repro, env: dict[str, str], artifacts: Path | None) -> None:
    if artifacts is None:
        return
    source = repro.shared_home(env)
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in ("logs", "updates"):
        folder = source / name
        if folder.is_dir():
            shutil.copytree(folder, artifacts / name, dirs_exist_ok=True)


def reset_scenario(repro, env: dict[str, str], clear_logs: bool) -> None:
    home = repro.shared_home(env)
    shutil.rmtree(home / "updates", ignore_errors=True)
    if clear_logs:
        shutil.rmtree(home / "logs", ignore_errors=True)


def run_success(repro, env: dict[str, str], python: Path, target_wheel: Path, method: str) -> None:
    reset_scenario(repro, env, clear_logs=True)
    repro.stage_wheel(env, target_wheel, TARGET, method)
    apply_child(repro, python, dict(env, PIP_NO_INDEX="1"))
    wait_for(
        repro,
        lambda: installed_version(repro, python, env) == TARGET,
        f"{method} installed version {TARGET}",
    )
    updates = repro.shared_home(env) / "updates"
    logs = repro.shared_home(env) / "logs"
    wait_for(repro, lambda: not (updates / "applying.json").exists(), f"{method} helper")
    wait_for(
        repro,
        lambda: any(
            "returncode: 0" in path.read_text(encoding="utf-8") for path in logs.glob("*.log")
        ),
        f"{method} success log",
    )
    if (updates / "staged.json").exists():
        raise SystemExit(f"{method} success left the staged marker behind")
    print(f"{method} success: {PRIOR} -> {TARGET}")


def run_failure(repro, env: dict[str, str], python: Path, root: Path, method: str) -> None:
    reset_scenario(repro, env, clear_logs=False)
    bad = root / f"lazyplan_tui-{BAD}-py3-none-any.whl"
    bad.write_text("not a wheel\n", encoding="utf-8")
    repro.stage_wheel(env, bad, BAD, method)
    apply_child(repro, python, env)
    failed = repro.shared_home(env) / "updates" / "failed.json"
    wait_for(repro, failed.exists, f"{method} failure record")
    error = json.loads(failed.read_text(encoding="utf-8")).get("error", "")
    if "install" not in str(error).lower() and "wheel" not in str(error).lower():
        raise SystemExit(f"{method} failure record is not useful: {error!r}")
    if installed_version(repro, python, env) != TARGET:
        raise SystemExit(f"{method} failed apply changed the installed version")
    print(f"{method} failure: old version v{TARGET} still runs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--pipx", default=shutil.which("pipx") or "")
    parser.add_argument("--artifacts", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.pipx:
        print("pipx is required on PATH", file=sys.stderr)
        return 2
    repro = load_repro()
    root = Path(tempfile.mkdtemp(prefix="lazyplan-update-smoke-"))
    env = None
    try:
        env = repro.isolated_env(root, args.pipx)
        prior_wheel = repro.build_wheel(args.python, root / "prior", PRIOR)
        target_wheel = repro.build_wheel(args.python, root / "target", TARGET)
        repro.run(
            [args.pipx, "install", "--backend", "pip", str(prior_wheel)],
            env=env,
        )
        venv = Path(env["PIPX_HOME"]) / "venvs" / PACKAGE
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise SystemExit(f"cannot find the pipx venv python: {python}")
        if installed_version(repro, python, env) != PRIOR:
            raise SystemExit("prior wheel did not install")
        run_success(repro, env, python, target_wheel, "pipx")
        run_failure(repro, env, python, root, "pipx")

        venv_root = root / "venv"
        repro.run([args.python, "-m", "venv", str(venv_root)], env=env)
        venv_python = venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        repro.run(
            [str(venv_python), "-m", "pip", "install", str(prior_wheel)],
            env=env,
        )
        if installed_version(repro, venv_python, env) != PRIOR:
            raise SystemExit("prior wheel did not install in the venv")
        run_success(repro, env, venv_python, target_wheel, "venv")
        run_failure(repro, env, venv_python, root, "venv")
        return 0
    finally:
        if env is not None:
            copy_artifacts(repro, env, args.artifacts)
        if args.artifacts is None:
            shutil.rmtree(root, ignore_errors=True)
        else:
            repro.log(f"kept workspace: {root}")


if __name__ == "__main__":
    raise SystemExit(main())
