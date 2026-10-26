"""Deterministic performance benchmark for the TUI, store, and CLI reads.

Builds a throwaway journal with fixed row counts, then measures the read paths
that dominate normal use. The fixture is deliberately shaped like a multi-year
journal: many plans, nested milestones/tasks, criteria, commit links, repo
links, and events. Nothing outside the temporary directory is written.

Run it by hand:

    python3 tools/perf_bench.py
    python3 tools/perf_bench.py --quick
    python3 tools/perf_bench.py --no-tui --repeat 3

The benchmark reports wall time, SQL statement count, and connection count.
Budget enforcement lives in a later milestone; this tool only measures.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import lazyplan.store as store_mod  # noqa: E402
from lazyplan import audit, render, services, stats  # noqa: E402
from lazyplan.store import Store  # noqa: E402

STAMP = 1_700_000_000.0
DAY = 86_400.0
ARCHIVE_AGE = 30 * DAY


@dataclass(frozen=True)
class FixtureCounts:
    """Exact row counts for the benchmark journal."""

    plans: int = 88
    milestones: int = 275
    tasks: int = 789
    criteria: int = 2_095
    events: int = 10_703
    links: int = 708
    repos: int = 132
    archived_plans: int = 48
    doing_tasks: int = 4
    blocked_tasks: int = 3
    open_criteria: int = 6


DEFAULT_COUNTS = FixtureCounts()
QUICK_COUNTS = FixtureCounts(
    plans=8,
    milestones=20,
    tasks=50,
    criteria=120,
    events=600,
    links=40,
    repos=12,
    archived_plans=4,
    doing_tasks=2,
    blocked_tasks=2,
    open_criteria=4,
)


@dataclass(frozen=True)
class Fixture:
    """Built journal plus the ids the benchmark uses for focused reads."""

    db: Path
    counts: dict[str, int]
    first_plan_id: int
    first_task_id: int
    git_repo: Path | None


@dataclass(frozen=True)
class Measurement:
    """One timed read path."""

    name: str
    ms: float | None
    queries: int | None
    connections: int | None
    note: str = ""


@dataclass(frozen=True)
class Budget:
    """Exact query ceiling plus a generous Linux wall ceiling."""

    queries: int
    ms: float


# These are the pre-optimization ceilings. Tighten them as each milestone lands;
# task 876 owns the final cross-platform table. Query counts are exact and
# deterministic, so any accidental per-row query breaks the gate immediately.
BUDGETS: dict[str, Budget] = {
    "services.tree": Budget(950, 2_000),
    "services.tree_limit5": Budget(950, 2_000),
    "attention_ids": Budget(2_400, 2_000),
    "list_text": Budget(1_900, 3_000),
    "list_json": Budget(8_000, 6_000),
    "show_plan": Budget(200, 1_000),
    "export_all": Budget(19_000, 15_000),
    "audit_report": Budget(4_900, 6_000),
    "tui_refresh": Budget(5_300, 8_000),
    "git_status": Budget(0, 3_000),
    "git_show": Budget(0, 3_000),
}

# Wall time is noisy across hosted runners and Windows spawns are much dearer.
# Query counts are the hard gate; these ceilings catch sleeps, network waits,
# and accidental whole-database scans rather than small runner variance.
WALL_MULTIPLIER = {"linux": 1.0, "darwin": 2.0, "win32": 4.0}
OPTIONAL_METRICS = {"git_status", "git_show"}


def _split(total: int, buckets: int) -> list[int]:
    """Distribute `total` rows across `buckets` as evenly as possible."""
    if buckets <= 0:
        if total:
            raise ValueError("cannot distribute rows across zero buckets")
        return []
    base, extra = divmod(total, buckets)
    return [base + (1 if index < extra else 0) for index in range(buckets)]


def _sha(index: int, prefix: str = "commit") -> str:
    return hashlib.sha1(f"{prefix}-{index}".encode()).hexdigest()


def _insert_events(
    store: Store,
    rows: list[tuple[float, str, str, str, str]],
) -> None:
    """Insert deterministic event rows in one transaction."""
    if not rows:
        return
    with store._connect() as conn:
        conn.executemany(
            "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?,?,?,?,?)",
            rows,
        )


def _raw_counts(store: Store) -> dict[str, int]:
    """Exact table counts without going through a per-table Store helper."""
    tables = ("plans", "milestones", "tasks", "criteria", "events", "vcs_links", "entity_repos")
    with store._connect() as conn:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
            for table in tables
        }


def _set_statuses(
    store: Store,
    tasks: list,
    counts: FixtureCounts,
) -> None:
    """Mark the journal done, then seed doing/blocked rows for attention."""
    if counts.doing_tasks + counts.blocked_tasks > len(tasks):
        raise ValueError("doing + blocked tasks exceed the task count")
    with store._connect() as conn:
        conn.execute("UPDATE plans SET status='done'")
        conn.execute("UPDATE milestones SET status='done'")
        conn.execute("UPDATE tasks SET status='done'")
        for task in tasks[: counts.doing_tasks]:
            conn.execute("UPDATE tasks SET status='doing' WHERE id=?", (task.id,))
        start = counts.doing_tasks
        for task in tasks[start : start + counts.blocked_tasks]:
            conn.execute(
                "UPDATE tasks SET blocked=1, blocked_reason=? WHERE id=?",
                ("benchmark blocked", task.id),
            )


def _pad_events(
    store: Store,
    counts: FixtureCounts,
    plans: list,
    tasks: list,
) -> None:
    """Add the status evidence the read paths need, then exact-count filler."""
    required: list[tuple[float, str, str, str, str]] = []
    for plan in plans[: counts.archived_plans]:
        required.append(
            (
                STAMP - ARCHIVE_AGE,
                "bench",
                "plan",
                "status",
                f"plan #{plan.id} -> done (rollup)",
            )
        )
    for task in tasks[: counts.doing_tasks]:
        required.append(
            (STAMP - ARCHIVE_AGE, "bench", "task", "status", f"task #{task.id} -> doing")
        )
    with store._connect() as conn:
        generated = int(conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"])
    if generated + len(required) > counts.events:
        raise ValueError(
            f"fixture generates {generated + len(required)} events, "
            f"more than the requested {counts.events}"
        )
    _insert_events(store, required)
    filler = counts.events - generated - len(required)
    _insert_events(
        store,
        [
            (STAMP - DAY + index, "bench", "bench", "filler", f"filler {index + 1:05d}")
            for index in range(filler)
        ],
    )


def _make_git_repo(base: Path) -> Path | None:
    """One-commit repo for git status/show measurements; None without git."""
    if shutil.which("git") is None:
        return None
    repo = base / "git-repo"
    repo.mkdir(parents=True)
    commands = (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "bench@example.test"],
        ["git", "config", "user.name", "Bench"],
    )
    for command in commands:
        subprocess.run(command, cwd=repo, check=True, capture_output=True, timeout=30)
    (repo / "work.txt").write_text("bench\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "work.txt"], cwd=repo, check=True, capture_output=True, timeout=30
    )
    subprocess.run(
        ["git", "commit", "-qm", "bench commit"],
        cwd=repo,
        check=True,
        capture_output=True,
        timeout=30,
    )
    return repo


def build_fixture(
    db_path: str | Path,
    counts: FixtureCounts = DEFAULT_COUNTS,
) -> Fixture:
    """Build the deterministic journal at `db_path` and return its ids/counts."""
    if counts.plans <= 0 or counts.milestones <= 0 or counts.tasks <= 0:
        raise ValueError("fixture needs at least one plan, milestone, and task")
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with mock.patch("lazyplan.store.time.time", return_value=STAMP):
        store = Store(db)
        plans = [
            store.add_plan(
                f"Plan {index + 1:03d}",
                f"Benchmark plan {index + 1}",
                goal=f"Ship slice {index + 1}",
                actor="bench",
            )
            for index in range(counts.plans)
        ]

        milestones = []
        for plan, plan_count in zip(plans, _split(counts.milestones, counts.plans), strict=True):
            for index in range(plan_count):
                milestones.append(
                    store.add_milestone(
                        plan.id,
                        f"Milestone {len(milestones) + 1:03d}",
                        f"Slice {index + 1} of plan {plan.id}",
                        actor="bench",
                    )
                )

        tasks = []
        for milestone, milestone_count in zip(
            milestones, _split(counts.tasks, len(milestones)), strict=True
        ):
            for index in range(milestone_count):
                tasks.append(
                    store.add_task(
                        milestone.id,
                        f"Task {len(tasks) + 1:03d}",
                        f"Unit {index + 1} of milestone {milestone.id}",
                        actor="bench",
                    )
                )

        parents = [("plan", plan.id) for plan in plans]
        parents.extend(("milestone", milestone.id) for milestone in milestones)
        parents.extend(("task", task.id) for task in tasks)
        open_count = min(counts.open_criteria, len(tasks))
        for task in tasks[:open_count]:
            store.add_criteria("task", task.id, f"Open criterion for task {task.id}", actor="bench")
        remaining = counts.criteria - open_count
        if remaining < 0:
            raise ValueError("criteria count is smaller than open_criteria")
        for index in range(remaining):
            kind, obj_id = parents[index % len(parents)]
            criterion = store.add_criteria(
                kind,
                obj_id,
                f"Criterion {index + 1:04d}",
                actor="bench",
            )
            store.set_criteria(criterion.id, True, actor="bench")

        for index in range(counts.links):
            task = tasks[index % len(tasks)]
            repo_index = index % max(counts.repos, 1)
            store.link_commit(
                "task",
                task.id,
                _sha(index),
                subject=f"Commit {index + 1:03d}",
                author="Bench",
                timestamp=int(STAMP) + index,
                repo_root=str(db.parent / "repos" / f"repo-{repo_index}"),
                files=(f"src/file_{index % 7}.py",),
                actor="bench",
            )

        for index in range(counts.repos):
            task = tasks[index % len(tasks)]
            store.add_repo_link(
                "task",
                task.id,
                str(db.parent / "repos" / f"repo-{index}"),
                f"git@example.com:bench/repo-{index}.git",
                branch="main",
                base_sha=_sha(index, "base"),
                actor="bench",
            )

        _set_statuses(store, tasks, counts)
        _pad_events(store, counts, plans, tasks)
        raw = _raw_counts(store)

    expected = {
        "plans": counts.plans,
        "milestones": counts.milestones,
        "tasks": counts.tasks,
        "criteria": counts.criteria,
        "events": counts.events,
        "vcs_links": counts.links,
        "entity_repos": counts.repos,
    }
    if raw != expected:
        raise AssertionError(f"fixture counts {raw} != requested {expected}")
    return Fixture(
        db=db,
        counts=raw,
        first_plan_id=plans[0].id,
        first_task_id=tasks[0].id,
        git_repo=None,
    )


@contextmanager
def sql_counter() -> Iterator[dict[str, int]]:
    """Count statements and connections while a function runs."""
    original = store_mod.sqlite3.connect
    state = {"queries": 0, "connections": 0}

    def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = original(*args, **kwargs)  # type: ignore[arg-type]
        state["connections"] += 1

        def trace(_sql: str) -> None:
            state["queries"] += 1

        connection.set_trace_callback(trace)
        return connection

    store_mod.sqlite3.connect = connect  # type: ignore[assignment]
    try:
        yield state
    finally:
        store_mod.sqlite3.connect = original  # type: ignore[assignment]


def _timed(fn: Callable[[], object], repeat: int) -> float:
    """Best of `repeat` warm runs, in milliseconds."""
    for _ in range(repeat):
        fn()
    best = float("inf")
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - start) * 1_000)
    return best


def measure(
    name: str,
    fn: Callable[[], object],
    *,
    repeat: int = 1,
    trace: bool = True,
) -> Measurement:
    """Time one read path and optionally count its SQL/connections."""
    best = _timed(fn, max(1, repeat))
    queries = connections = None
    if trace:
        with sql_counter() as state:
            fn()
        queries = state["queries"]
        connections = state["connections"]
    return Measurement(name, round(best, 1), queries, connections)


def _core_metrics(store: Store, fixture: Fixture, repeat: int) -> list[Measurement]:
    from lazyplan.cli import _list_payload

    return [
        measure("services.tree", lambda: services.tree(store), repeat=repeat),
        measure("services.tree_limit5", lambda: services.tree(store, limit=5), repeat=repeat),
        measure("attention_ids", lambda: stats.attention_ids(store), repeat=repeat),
        measure(
            "list_text",
            lambda: render.summary_lines(store, None, None, limit=5),
            repeat=repeat,
        ),
        measure(
            "list_json",
            lambda: _list_payload(store, None, "hide", None, None, None, None),
            repeat=repeat,
        ),
        measure("show_plan", lambda: store.get_full("plan", fixture.first_plan_id), repeat=repeat),
        measure("export_all", lambda: services.export_all(store), repeat=repeat),
        measure(
            "audit_report",
            lambda: audit.report(store, since=STAMP - ARCHIVE_AGE),
            repeat=repeat,
        ),
    ]


def _git_metrics(repo: Path | None, repeat: int) -> list[Measurement]:
    if repo is None:
        note = "git not installed"
        return [
            Measurement("git_status", None, None, None, note),
            Measurement("git_show", None, None, None, note),
        ]
    from lazyplan.vcs import detect_backend

    backend, root = detect_backend(repo)
    if backend is None or root is None:
        note = "no VCS backend"
        return [
            Measurement("git_status", None, None, None, note),
            Measurement("git_show", None, None, None, note),
        ]
    head = backend.head(root)
    if head is None:
        note = "git repo has no HEAD"
        return [
            Measurement("git_status", None, None, None, note),
            Measurement("git_show", None, None, None, note),
        ]
    return [
        measure("git_status", lambda: backend.status(root), repeat=repeat, trace=False),
        measure("git_show", lambda: backend.show(root, head), repeat=repeat, trace=False),
    ]


def _tui_measurement(db: Path, repeat: int) -> Measurement:
    try:
        from lazyplan import tui
        from lazyplan.upgrade import UpgradeError
    except ImportError:
        return Measurement("tui_refresh", None, None, None, "textual not installed")

    old_spinner = os.environ.get("LAZYPLAN_NO_SPINNER")
    os.environ["LAZYPLAN_NO_SPINNER"] = "1"
    try:

        async def run() -> Measurement:
            app = tui.create_app(str(db))
            with mock.patch.object(
                tui, "latest_version", side_effect=UpgradeError("benchmark offline")
            ):
                async with app.run_test(size=(120, 40)) as pilot:
                    await pilot.pause()
                    for _ in range(max(1, repeat)):
                        app.refresh_all()
                    best = float("inf")
                    for _ in range(max(1, repeat)):
                        start = time.perf_counter()
                        app.refresh_all()
                        best = min(best, (time.perf_counter() - start) * 1_000)
                    with sql_counter() as state:
                        app.refresh_all()
                    return Measurement(
                        "tui_refresh",
                        round(best, 1),
                        state["queries"],
                        state["connections"],
                    )

        return asyncio.run(run())
    finally:
        if old_spinner is None:
            os.environ.pop("LAZYPLAN_NO_SPINNER", None)
        else:
            os.environ["LAZYPLAN_NO_SPINNER"] = old_spinner


def run(
    counts: FixtureCounts = DEFAULT_COUNTS,
    *,
    repeat: int = 1,
    include_tui: bool = True,
) -> dict:
    """Build a throwaway fixture and return fixture counts plus measurements."""
    with tempfile.TemporaryDirectory(prefix="lazyplan-perf-") as tmp:
        base = Path(tmp)
        fixture = build_fixture(base / "lazyplan.db", counts)
        store = Store(fixture.db)
        metrics = _core_metrics(store, fixture, max(1, repeat))
        metrics.extend(_git_metrics(_make_git_repo(base), max(1, repeat)))
        if include_tui:
            metrics.append(_tui_measurement(fixture.db, max(1, repeat)))
        else:
            metrics.append(Measurement("tui_refresh", None, None, None, "disabled by --no-tui"))
        return {
            "fixture": fixture.counts,
            "metrics": [asdict(metric) for metric in metrics],
        }


def summary(result: dict) -> list[str]:
    """Readable metric table for humans."""
    lines = ["metric                  ms      queries  connections"]
    for metric in result["metrics"]:
        ms = "-" if metric["ms"] is None else f"{metric['ms']:.1f}"
        queries = "-" if metric["queries"] is None else str(metric["queries"])
        connections = "-" if metric["connections"] is None else str(metric["connections"])
        line = f"{metric['name']:<22} {ms:>7} {queries:>9} {connections:>12}"
        if metric["note"]:
            line += f"  ({metric['note']})"
        lines.append(line)
    return lines


def check(result: dict, budgets: dict[str, Budget] | None = None) -> list[str]:
    """Return one message per budget breach; an empty list means all clear."""
    budgets = BUDGETS if budgets is None else budgets
    metrics = {metric["name"]: metric for metric in result["metrics"]}
    multiplier = WALL_MULTIPLIER.get(sys.platform, 3.0)
    failures: list[str] = []
    for name, budget in budgets.items():
        metric = metrics.get(name)
        if metric is None:
            failures.append(f"{name}: metric was not measured")
            continue
        if metric["queries"] is None:
            if name in OPTIONAL_METRICS:
                continue
            failures.append(f"{name}: query count unavailable ({metric['note'] or 'untraced'})")
            continue
        if metric["queries"] > budget.queries:
            failures.append(f"{name}: {metric['queries']} queries > {budget.queries}")
        if metric["ms"] is None:
            if name in OPTIONAL_METRICS:
                continue
            failures.append(f"{name}: wall time unavailable")
            continue
        ceiling = budget.ms * multiplier
        if metric["ms"] > ceiling:
            failures.append(f"{name}: {metric['ms']:.1f}ms > {ceiling:.1f}ms")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="use the small test fixture")
    parser.add_argument("--repeat", type=int, default=1, help="timed runs per metric")
    parser.add_argument("--no-tui", action="store_true", help="skip the headless TUI refresh")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when a query or wall budget regresses",
    )
    args = parser.parse_args(argv)
    result = run(
        QUICK_COUNTS if args.quick else DEFAULT_COUNTS,
        repeat=max(1, args.repeat),
        include_tui=not args.no_tui,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result["fixture"], indent=2))
        print()
        print("\n".join(summary(result)))
    if not args.check:
        return 0
    failures = check(result)
    if failures:
        print("\nperformance budget failures:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("\nperformance budgets: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
