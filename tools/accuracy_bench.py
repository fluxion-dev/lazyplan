"""Synthetic accuracy benchmark: same work, with and without hook reminders.

Builds a throwaway git repo and two throwaway databases, replays eight
commits, and compares audit metrics. Deterministic, offline, and safe to run
from tests or by hand:

    python3 tools/accuracy_bench.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lazyplan import audit, hooks, services  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402

COMMITS = 8
SLICE = 4


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _make_repo(path: Path) -> Path:
    """Eight commits at fixed one-hour offsets, ending near now."""
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "bench@example.test")
    _git(path, "config", "user.name", "Bench")
    base = datetime.now(UTC) - timedelta(hours=COMMITS)
    for index in range(COMMITS):
        stamp = base + timedelta(hours=index)
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = stamp.isoformat()
        env["GIT_COMMITTER_DATE"] = stamp.isoformat()
        (path / "work.txt").write_text(f"step {index}\n", encoding="utf-8", newline="\n")
        _git(path, "add", "work.txt")
        _git(path, "commit", "-qm", f"step {index}", env=env)
    return path


def _seed(home: Path, repo: Path) -> tuple[Store, int, int, int]:
    """Plan with two four-commit tasks and one open criterion on task B."""
    store = Store(home / ".lazyplan/lazyplan.db")
    plan = store.add_plan("Bench", "what", goal="why")
    milestone = store.add_milestone(plan.id, "M", "desc")
    task_a = store.add_task(milestone.id, "Slice A", "first four")
    task_b = store.add_task(milestone.id, "Slice B", "last four")
    store.add_criteria("task", task_b.id, "finish the last slice")
    return store, plan.id, task_a.id, task_b.id


def _status(store: Store, kind: str, obj_id: int, status: Status, when: float) -> None:
    with mock.patch("lazyplan.store.time.time", return_value=when):
        services.set_status(store, kind, obj_id, status, actor="bench")


def _link(store: Store, task_id: int, commit: audit.Commit) -> None:
    store.link_commit(
        "task",
        task_id,
        commit.sha,
        subject=commit.subject,
        timestamp=commit.timestamp,
        actor="bench",
    )


def _commits(store: Store, plan_id: int, repo: Path) -> list[audit.Commit]:
    commits, _repos = audit.gather_commits(store, [plan_id], 0, repo)
    return sorted(commits, key=lambda item: item.timestamp)


def _baseline(home: Path, repo: Path) -> dict:
    store, plan_id, task_a, task_b = _seed(home, repo)
    commits = _commits(store, plan_id, repo)
    now = datetime.now(UTC).timestamp()
    for commit in commits[:2]:
        _link(store, task_a, commit)
    _status(store, "task", task_a, Status.DOING, commits[0].timestamp + 60)
    _status(store, "task", task_a, Status.DONE, now)
    _status(store, "task", task_b, Status.DOING, now)
    _status(store, "task", task_b, Status.DONE, now)
    return audit.report(store, [plan_id], 0, repo).to_dict()


def _intervention(home: Path, repo: Path) -> dict:
    store, plan_id, task_a, task_b = _seed(home, repo)
    commits = _commits(store, plan_id, repo)
    old_cwd = os.getcwd()
    old_db = os.environ.get("LAZYPLAN_DB")
    os.chdir(repo)
    os.environ["LAZYPLAN_DB"] = str(store.path)
    task = task_a
    try:
        _status(store, "task", task_a, Status.DOING, commits[0].timestamp + 60)
        for index, commit in enumerate(commits):
            reminder = hooks.build_result(
                "post-tool",
                {"tool_input": {"command": "git commit -m step"}},
                repo,
                commits=[],
            )
            if reminder.text:
                _link(store, task, commit)
            if index == SLICE - 1:
                _status(store, "task", task_a, Status.DONE, commit.timestamp + 120)
                _status(store, "task", task_b, Status.DOING, commit.timestamp + 180)
                task = task_b
            if index == COMMITS - 1:
                for item in store.open_criteria("task", task_b):
                    store.set_criteria(item.id, True, actor="bench")
                _status(store, "task", task_b, Status.DONE, commit.timestamp + 120)
    finally:
        os.chdir(old_cwd)
        if old_db is None:
            os.environ.pop("LAZYPLAN_DB", None)
        else:
            os.environ["LAZYPLAN_DB"] = old_db
    return audit.report(store, [plan_id], 0, repo).to_dict()


def run() -> dict:
    """Run both scenarios in throwaway homes and return their audits."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        repo = _make_repo(base / "repo")
        baseline = _baseline(base / "baseline", repo)
        intervention = _intervention(base / "intervention", repo)
    return {"baseline": baseline, "intervention": intervention}


def summary(result: dict) -> list[str]:
    """Two-row table for humans."""
    lines = ["scenario       coverage  lag(commits)  gaps"]
    for name in ("baseline", "intervention"):
        row = result[name]
        lines.append(
            f"{name:<14} {row['coverage']:>7.0%}  {row['median_lag_commits']:>11g}  "
            f"{len(row['criteria_gaps']):>4}"
        )
    return lines


def main() -> int:
    result = run()
    print(json.dumps(result, indent=2))
    print()
    print("\n".join(summary(result)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
