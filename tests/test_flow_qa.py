"""Flow-health QA: stats and Attention agree on the same fixture."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services, stats  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestFlowQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "flow.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.ids = {}
        for name in ("blocked", "expired", "aging", "gap", "red", "fresh", "plain"):
            self.ids[name] = self.store.add_task(milestone.id, name, "desc", actor="fixture").id
        self.store.set_blocked(self.ids["blocked"], True, "waiting", actor="fixture")
        self.store.claim_task(self.ids["expired"], "alice", 1, now=1)
        with mock.patch("lazyplan.store.time.time", return_value=1):
            services.set_status(
                self.store, "task", self.ids["aging"], Status.DOING, actor="fixture"
            )
        self.store.add_criteria("task", self.ids["gap"], "open", actor="fixture")
        services.set_status(self.store, "task", self.ids["gap"], Status.DONE, actor="fixture")
        self.store.link_forge(
            "task", self.ids["red"], 7, checks="fail", title="red", actor="fixture"
        )
        services.set_status(self.store, "task", self.ids["fresh"], Status.DOING, actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_attention_and_stats_agree(self):
        attention = stats.attention_ids(self.store, now=time.time())
        self.assertEqual(
            attention,
            {
                self.ids["blocked"],
                self.ids["expired"],
                self.ids["aging"],
                self.ids["gap"],
                self.ids["red"],
            },
        )
        result = stats.compute(self.store, since=0, stale_before=0, now=time.time())
        self.assertEqual(result["wip"], 2)
        self.assertEqual(result["blocked"], 1)
        self.assertEqual(result["throughput"], 1)
        self.assertEqual(result["claims"], 0)  # expired lease is not active

    def test_stats_porcelain_is_six_columns(self):
        result = stats.compute(self.store, since=0, stale_before=0, now=time.time())
        self.assertEqual(
            [key for key in result if key not in ("since", "actor")],
            [
                "wip",
                "cycle_median_minutes",
                "throughput",
                "aging_median_minutes",
                "aging_max_minutes",
                "stale_todos",
                "reopened",
                "claims",
                "blocked",
            ],
        )


if __name__ == "__main__":
    unittest.main()
