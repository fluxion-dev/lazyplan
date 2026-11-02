"""The insights facade exposes the read models every surface uses."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import insights
from lazyplan.store import Store


class TestInsightsFacade(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "insights.db"))
        self.plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(self.plan.id, "M", actor="fixture")
        self.store.add_task(
            milestone.id, "T", "Commit slice: one.\n\nVerification: test.", actor="fixture"
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_metrics_snapshot_is_available(self) -> None:
        snapshot = insights.metrics.snapshot(self.store, now=1000.0, plan_id=self.plan.id)
        self.assertEqual(snapshot.plan_title, "P")

    def test_audit_window_and_stats_are_available(self) -> None:
        self.assertIsNone(insights.audit.parse_since(""))
        stats = insights.stats.compute(self.store, since=0.0, stale_before=1000.0, now=1000.0)
        self.assertIn("wip", stats)

    def test_lint_and_brief_are_available(self) -> None:
        self.assertIsNotNone(insights.brief.build(self.store, self.plan.id))
        self.assertEqual(insights.lint.lint_plan(self.store, self.plan.id), [])


if __name__ == "__main__":
    unittest.main()
