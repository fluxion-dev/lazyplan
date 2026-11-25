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
        milestone = self.store.add_milestone(
            self.plan.id,
            "M",
            (
                "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
                "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
                "Inputs: The approved definition and the scouted code path.\n\n"
                "Slices: Implement and verify in separate green commits."
            ),
            actor="fixture",
        )
        self.store.add_task(
            milestone.id,
            "T",
            (
                "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
                "Touch: src/app.py, tests/test_app.py\n\n"
                "Inputs: The approved definition; none beyond the plan scope.\n\n"
                "Commit: One implementation slice.\n\n"
                "Verify: The relevant test suite passes.\n\n"
                "Guardrails: Keep behavior outside the reviewed scope unchanged."
            ),
            actor="fixture",
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
