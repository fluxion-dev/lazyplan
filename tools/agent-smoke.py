#!/usr/bin/env python3
"""Live agent smoke: exact identity, then lost after the host is killed.

Runs the real CLI against a temporary repository and database. The fake host
is a sleeping process whose PID rides on the hook payload; killing it and
running one sweep proves the liveness path without touching a real agent.
Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

PROFILES = {
    "opencode": {
        "argv": ["hook", "session-start", "--host", "opencode"],
        "payload": {"sessionID": "smoke-opencode", "agent": "smoke", "model": "smoke-model"},
    },
    "claude": {
        "argv": ["hook", "session-start", "--host", "claude"],
        "payload": {
            "session_id": "smoke-claude",
            "hook_event_name": "SessionStart",
            "agent": "smoke",
            "model": "smoke-model",
        },
    },
}


def _run(
    argv: list[str], env: dict[str, str], stdin: str = "", cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one CLI command and return its completed process."""
    return subprocess.run(
        argv,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=cwd,
        timeout=60,
        check=False,
    )


def _cli(
    env: dict[str, str], *args: str, stdin: str = "", cwd: Path | None = None
) -> str:
    """Run the module CLI and return stdout, failing on a non-zero exit."""
    result = _run([sys.executable, "-m", "lazyplan", *args], env, stdin, cwd)
    if result.returncode != 0:
        raise SystemExit(f"lpui {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def main() -> int:
    """Run the smoke for every host profile in a disposable checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="keep the temporary checkout")
    args = parser.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="lazyplan-agent-smoke-"))
    repo = tmp / "repo"
    worktree = tmp / "worktree"
    repo.mkdir()
    db = tmp / "smoke.db"
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "smoke@example.com")
    _git(repo, "config", "user.name", "Smoke")
    (repo / "file.txt").write_text("smoke\n", encoding="utf-8")
    _git(repo, "add", "file.txt")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "worktree", "add", "-q", "-b", "plan/1-smoke", str(worktree))
    env = dict(os.environ, PYTHONPATH=str(SRC), LAZYPLAN_NO_SETUP="1")
    dbarg = ["--db", str(db), "--json", "--actor", "smoke"]
    _cli(env, *dbarg, "plan", "add", "--title", "Smoke", "--why", "verify", "--what", "verify")
    _cli(env, *dbarg, "milestone", "add", "--plan", "1", "--title", "M")
    _cli(env, *dbarg, "task", "add", "--milestone", "1", "--title", "T")
    _cli(env, *dbarg, "link-repo", "--kind", "plan", "--id", "1", "--repo", str(repo))
    _cli(
        env,
        *dbarg,
        "plan",
        "worktree",
        "add",
        "--id",
        "1",
        "--repo",
        str(repo),
        "--worktree",
        str(worktree),
    )
    _cli(env, *dbarg, "claim", "--id", "1", "--ttl", "30m", cwd=worktree)
    failures: list[str] = []
    try:
        for host, profile in PROFILES.items():
            host_proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(120)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                payload = dict(profile["payload"], pid=host_proc.pid, cwd=str(worktree))
                _cli(env, *dbarg, *profile["argv"], stdin=json.dumps(payload), cwd=worktree)
                listed = json.loads(_cli(env, *dbarg, "agent", "list", "--open"))
                if not listed:
                    failures.append(f"{host}: no agent row")
                    continue
                agent = listed[0]
                for field in (
                    "host",
                    "host_session",
                    "agent",
                    "role",
                    "model",
                    "parent_id",
                    "pid",
                    "repo_path",
                    "worktree",
                    "branch",
                    "head_sha",
                    "plan_id",
                    "task_id",
                    "status",
                ):
                    if field not in agent:
                        failures.append(f"{host}: missing {field}")
                if agent["host"] != host:
                    failures.append(f"{host}: host is {agent['host']}")
                if agent["plan_id"] != 1:
                    failures.append(f"{host}: plan is {agent['plan_id']}")
                if agent["task_id"] != 1:
                    failures.append(f"{host}: task is {agent['task_id']}")
                host_proc.kill()
                host_proc.wait(timeout=10)
                _cli(env, *dbarg, "agent", "sweep")
                lost = json.loads(_cli(env, *dbarg, "agent", "show", "--id", f"A{agent['id']}"))
                if lost["agent"]["status"] != "lost":
                    failures.append(f"{host}: status is {lost['agent']['status']}, not lost")
            finally:
                if host_proc.poll() is None:
                    host_proc.kill()
                    host_proc.wait(timeout=10)
    finally:
        if args.keep:
            print(f"kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("agent smoke ok: exact identity, then lost")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
