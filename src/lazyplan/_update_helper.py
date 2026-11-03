"""Detached Windows update helper: wait for the parent, install, log, restart."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .infrastructure import update_log, update_stage
from .infrastructure.update_apply import ApplyPlan, wait_for_parent

HELPER_TIMEOUT = 300.0
PARENT_TIMEOUT = 60.0


def _log(
    plan: ApplyPlan,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    extra: dict[str, object] | None = None,
) -> None:
    try:
        update_log.record_update(
            "apply",
            method=plan.method,
            command=plan.command,
            cwd=Path.cwd(),
            exe=plan.python,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            extra=extra,
            path=plan.log_path,
        )
    except OSError:
        pass


def _plan(payload: dict[str, Any]) -> ApplyPlan:
    home = payload.get("home")
    return ApplyPlan(
        wheel=Path(payload["wheel"]),
        method=str(payload["method"]),
        python=str(payload["python"]),
        pipx=str(payload.get("pipx", "")),
        command=tuple(str(part) for part in payload["command"]),
        restart=tuple(str(part) for part in payload.get("restart", [])),
        scripts=Path(payload["scripts"]),
        log_path=Path(payload["log"]),
        home=Path(home) if home else None,
        windows=bool(payload.get("windows", False)),
    )


def _setup_review(plan: ApplyPlan) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [plan.python, "-m", "lazyplan", "setup", "--post-upgrade"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=HELPER_TIMEOUT,
    )


def _restart(plan: ApplyPlan) -> None:
    if not plan.restart:
        return
    subprocess.Popen(plan.restart, close_fds=True)


def run(plan: ApplyPlan, parent_pid: int) -> int:
    """Wait for the parent, apply the wheel, and optionally restart."""
    if not wait_for_parent(parent_pid, timeout=PARENT_TIMEOUT):
        error = f"timed out waiting for lpui PID {parent_pid} to exit"
        _log(plan, None, stderr=error)
        update_stage.park_failure(error, plan.home)
        return 2
    try:
        result = subprocess.run(
            plan.command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HELPER_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        error = f"install failed: {exc}"
        _log(plan, None, stderr=error)
        update_stage.park_failure(error, plan.home)
        return 1
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "install failed").strip()
        _log(plan, result.returncode, result.stdout or "", result.stderr or "")
        update_stage.park_failure(error, plan.home)
        return 1
    update_stage.clear_apply(plan.home, plan.wheel)
    try:
        setup = _setup_review(plan)
        setup_code = setup.returncode
        setup_output = (setup.stdout or "") + (setup.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        setup_code = None
        setup_output = str(exc)
    _log(
        plan,
        result.returncode,
        result.stdout or "",
        result.stderr or "",
        extra={"setup_returncode": setup_code, "setup_output": setup_output.strip()},
    )
    _restart(plan)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--plan-json", required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.plan_json)
        plan = _plan(payload)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid update plan: {exc}", file=sys.stderr)
        return 2
    return run(plan, args.parent_pid)


if __name__ == "__main__":
    raise SystemExit(main())
