"""Flow stats: WIP, cycle time, throughput, aging, stale, reopened, claims."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import services, stats  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "stats.db")
        self.store = Store(self.db)
        with mock.patch("lazyplan.store.time.time", return_value=1000):
            plan = self.store.add_plan("P", actor="alice")
            milestone = self.store.add_milestone(plan.id, "M", actor="alice")
            self.t1 = self.store.add_task(
                milestone.id, "done", "Commit slice: one. Verification: test.", actor="alice"
            )
            self.t2 = self.store.add_task(
                milestone.id, "doing", "Commit slice: one. Verification: test.", actor="alice"
            )
            self.t3 = self.store.add_task(
                milestone.id, "stale", "Commit slice: one. Verification: test.", actor="alice"
            )
            self.t4 = self.store.add_task(
                milestone.id, "reopened", "Commit slice: one. Verification: test.", actor="alice"
            )
        self._status(self.t1.id, 1100, Status.DOING, "alice")
        self._status(self.t1.id, 1200, Status.DONE, "alice")
        self._status(self.t2.id, 1900, Status.DOING, "alice")
        self._status(self.t4.id, 1100, Status.DOING, "alice")
        self._status(self.t4.id, 1200, Status.DONE, "alice")
        self._status(self.t4.id, 1300, Status.DOING, "alice")
        with mock.patch("lazyplan.store.time.time", return_value=1900):
            self.store.claim_task(self.t2.id, "alice", ttl_seconds=600, now=1900)
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _status(self, tid: int, when: float, status: Status, actor: str) -> None:
        with mock.patch("lazyplan.store.time.time", return_value=when):
            services.set_status(self.store, "task", tid, status, actor=actor)

    def _compute(self) -> dict:
        return stats.compute(self.store, since=0, stale_before=1500, now=2000)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "alice", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_golden_metrics(self):
        self.assertEqual(
            self._compute(),
            {
                "since": 0,
                "actor": None,
                "wip": 2,
                "cycle_median_minutes": 1.7,
                "throughput": 2,
                "aging_median_minutes": 6.7,
                "aging_max_minutes": 11.7,
                "stale_todos": 1,
                "reopened": 1,
                "claims": 1,
                "blocked": 0,
            },
        )

    def test_metrics(self):
        result = self._compute()
        self.assertEqual(result["wip"], 2)
        self.assertEqual(result["throughput"], 2)
        self.assertEqual(result["cycle_median_minutes"], 1.7)
        self.assertEqual(result["aging_median_minutes"], 6.7)
        self.assertEqual(result["aging_max_minutes"], 11.7)
        self.assertEqual(result["stale_todos"], 1)
        self.assertEqual(result["reopened"], 1)
        self.assertEqual(result["claims"], 1)
        self.assertEqual(result["blocked"], 0)

    def test_actor_filter_only_changes_activity(self):
        result = stats.compute(self.store, since=0, stale_before=1500, actor="bob", now=2000)
        self.assertEqual(result["throughput"], 0)
        self.assertEqual(result["reopened"], 0)
        self.assertEqual(result["wip"], 2)
        result = stats.compute(self.store, since=0, stale_before=1500, actor="alice", now=2000)
        self.assertEqual(result["throughput"], 2)

    def test_cli_text_porcelain_json(self):
        code, out, err = self._run("stats", "--since", "2020-01-01", "--stale-after", "1.days")
        self.assertEqual(code, 0, err)
        self.assertIn("wip", out)
        self.assertIn("cycle", out)
        code, out, err = self._run(
            "--porcelain", "stats", "--since", "2020-01-01", "--stale-after", "1.days"
        )
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.rstrip("\n").splitlines()]
        self.assertTrue(all(len(row) == 6 for row in rows))
        self.assertIn("metric", {row[0] for row in rows})
        code, out, err = self._run(
            "--json", "stats", "--since", "2020-01-01", "--stale-after", "1.days"
        )
        payload = json.loads(out)
        self.assertEqual(payload["wip"], 2)

    def test_invalid_window_exits_two(self):
        code, out, err = self._run("stats", "--since", "not-a-date")
        self.assertEqual(code, 2)
        self.assertIn("invalid", err)

    def test_empty_window_is_zero_not_an_error(self):
        result = stats.compute(self.store, since=9999999999, stale_before=0, now=2000)
        self.assertEqual(result["throughput"], 0)
        self.assertEqual(result["cycle_median_minutes"], 0.0)


if __name__ == "__main__":
    unittest.main()
