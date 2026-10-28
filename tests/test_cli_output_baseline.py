"""Byte-exact baseline for default and --json CLI output.

Porcelain must be purely additive: every expectation here is what the CLI
printed before the mode existed and must keep printing unchanged. Update this
file on purpose when human or JSON output changes, never to make porcelain fit.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.services import set_status
from lazyplan.store import Store
from tests.support.home import sandbox_home

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cli" / "baseline.json"
BASELINE: dict[str, str] = json.loads(FIXTURE.read_text(encoding="utf-8"))

CASES: dict[str, list[str]] = {
    "list_default": ["list"],
    "list_tree_default": ["list", "--tree"],
    "list_json": ["--json", "list"],
    "plan_show_default": ["plan", "show", "--id", "1"],
    "plan_show_json": ["--json", "plan", "show", "--id", "1"],
    "task_add_default": [
        "task",
        "add",
        "--milestone",
        "1",
        "--title",
        "Build nav",
        "--desc",
        "Nav work",
    ],
    "task_add_json": [
        "--json",
        "task",
        "add",
        "--milestone",
        "1",
        "--title",
        "Build nav",
        "--desc",
        "Nav work",
    ],
    "task_move_default": ["task", "move", "--id", "1", "--to", "done"],
    "task_move_json": ["--json", "task", "move", "--id", "1", "--to", "done"],
    "criterion_add_default": [
        "criterion",
        "add",
        "--kind",
        "plan",
        "--id",
        "1",
        "--text",
        "Loads fast",
    ],
    "criterion_add_json": [
        "--json",
        "criterion",
        "add",
        "--kind",
        "plan",
        "--id",
        "1",
        "--text",
        "Loads fast",
    ],
    "brief_default": ["brief", "--plan", "1"],
    "brief_json": ["--json", "brief", "--plan", "1"],
    "audit_default": ["audit", "--plan", "1", "--since", "2026-01-01"],
    "audit_json": ["--json", "audit", "--plan", "1", "--since", "2026-01-01"],
    "feed_default": ["feed", "--limit", "3"],
    "feed_json": ["--json", "feed", "--limit", "3"],
}


def build_fixture(db: str) -> None:
    """Deterministic plan + milestone + doing task, with fixture-authored events."""
    store = Store(db)
    plan = store.add_plan("Website", "Marketing site", goal="Convert", actor="fixture")
    milestone = store.add_milestone(plan.id, "Homepage", "Hero work", actor="fixture")
    task = store.add_task(milestone.id, "Design hero", "Hero section", actor="fixture")
    set_status(store, "task", task.id, Status.DOING, actor="fixture")


LOCAL_TIME_CASES = {"audit_default"}


def _clock_is_utc() -> bool:
    return datetime.now().astimezone().utcoffset() == timedelta(0)


class TestCliBaseline(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.old_cwd = os.getcwd()
        self.old_tz = os.environ.get("TZ")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        os.environ["TZ"] = "UTC"
        if hasattr(time, "tzset"):
            time.tzset()

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        for key, value in (
            ("TZ", self.old_tz),
            ("LAZYPLAN_NO_SETUP", self.old_setup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if hasattr(time, "tzset"):
            time.tzset()
        self.tmp.cleanup()

    def _run(self, name: str) -> str:
        db = str(self.root / f"{name}.db")
        build_fixture(db)
        buf = io.StringIO()
        os.chdir(self.work)
        try:
            with contextlib.redirect_stdout(buf), mock.patch("sys.stdin", io.StringIO("")):
                code = lpui_main(["--db", db, "--actor", "fixture", *CASES[name]])
        finally:
            os.chdir(self.old_cwd)
        self.assertEqual(code, 0, name)
        out = buf.getvalue()
        out = re.sub(r'"ts": [0-9.]+', '"ts": <ts>', out)
        # Some commands report the resolved cwd; /var is a symlink to
        # /private/var on macOS, so normalize both spellings.
        roots = {self.tmp.name, os.path.realpath(self.tmp.name)}
        for raw in sorted(roots, key=len, reverse=True):
            out = out.replace(raw, "<tmp>")
            out = out.replace(json.dumps(raw)[1:-1], "<tmp>")
        return re.sub(r'<tmp>[^\s"]*', lambda m: re.sub(r"\\+", "/", m.group(0)), out)

    def test_every_baseline_case_is_pinned(self):
        self.assertEqual(set(CASES), set(BASELINE))

    def test_default_output_is_unchanged(self):
        for name in sorted(n for n in CASES if n.endswith("_default")):
            with self.subTest(name=name):
                if name in LOCAL_TIME_CASES and not _clock_is_utc():
                    self.skipTest("prints local time, and this platform cannot pin TZ=UTC")
                self.assertEqual(self._run(name), BASELINE[name])

    def test_json_output_is_unchanged(self):
        for name in sorted(n for n in CASES if n.endswith("_json")):
            with self.subTest(name=name):
                self.assertEqual(self._run(name), BASELINE[name])


if __name__ == "__main__":
    unittest.main()
