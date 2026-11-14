"""The needs-me read model: attention, health, sessions, claims, and overlaps."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import insights, revisions, stats
from lazyplan.store import Store

NOW = 1_000_100.0


class TestNeedsMe(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "needs-me.db"))
        self.plan = self.store.add_plan("Control room", actor="fixture")
        self.milestone = self.store.add_milestone(
            self.plan.id, "See the work", "As a human, I want triage.", actor="fixture"
        )
        self.tasks: dict[str, int] = {}
        for name in (
            "blocked",
            "stale",
            "aging",
            "gap",
            "red",
            "unclaimed",
            "overlap-a",
            "overlap-b",
            "fresh",
        ):
            self.tasks[name] = self.store.add_task(
                self.milestone.id, name, "Commit: one.\n\nVerify: tests.", actor="fixture"
            ).id
        self.store.set_blocked(self.tasks["blocked"], True, "waiting", actor="fixture")
        self.store.claim_task(self.tasks["stale"], "alice", 10, now=1)
        with mock.patch("lazyplan.store.base.time.time", return_value=1):
            services.set_status(
                self.store, "task", self.tasks["aging"], Status.DOING, actor="fixture"
            )
        self.store.release_claim(self.tasks["aging"], "fixture")
        self.store.add_criteria("task", self.tasks["gap"], "open", actor="fixture")
        services.set_status(self.store, "task", self.tasks["gap"], Status.DONE, actor="fixture")
        self.store.link_forge(
            "task",
            self.tasks["red"],
            7,
            checks="fail",
            state="open",
            title="red",
            actor="fixture",
        )
        with mock.patch("lazyplan.store.base.time.time", return_value=999_900):
            services.set_status(
                self.store, "task", self.tasks["unclaimed"], Status.DOING, actor="fixture"
            )
        self.store.release_claim(self.tasks["unclaimed"], "fixture")
        self.store.claim_task(self.tasks["overlap-a"], "alice", 10_000, now=1_000_000)
        self.store.claim_task(self.tasks["overlap-b"], "bob", 10_000, now=1_000_000)
        self.store.add_touchpoint(self.tasks["overlap-a"], "src/app", actor="fixture")
        self.store.add_touchpoint(self.tasks["overlap-b"], "src/app/api.py", actor="fixture")

        self.second = self.store.add_plan("Second plan", actor="fixture")
        self.store.add_milestone(
            self.second.id, "Ship it", "As a user, I want it.", actor="fixture"
        )
        revisions.approve(self.store, self.second.id, actor="fixture")
        self.store.update_plan(self.second.id, description="changed", actor="fixture")
        services.add_question(self.store, self.second.id, "Which host?", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self, **kwargs):
        return insights.needs_me.build(self.store, now=NOW, **kwargs)

    def test_attention_reasons_are_named(self) -> None:
        payload = self._build()
        rows = {row["task_id"]: row for row in payload["attention"]}
        self.assertEqual(rows[self.tasks["blocked"]]["reasons"], ["blocked"])
        self.assertEqual(rows[self.tasks["stale"]]["reasons"], ["stale claim"])
        self.assertEqual(rows[self.tasks["aging"]]["reasons"], ["aging doing", "unclaimed doing"])
        self.assertEqual(rows[self.tasks["unclaimed"]]["reasons"], ["unclaimed doing"])
        self.assertEqual(rows[self.tasks["gap"]]["reasons"], ["done with open criteria"])
        self.assertEqual(rows[self.tasks["red"]]["reasons"], ["failing checks"])
        self.assertNotIn(self.tasks["fresh"], rows)
        self.assertEqual(payload["counts"]["attention"], 6)

    def test_plan_health_rolls_up_questions_and_drift(self) -> None:
        payload = self._build()
        rows = {row["id"]: row for row in payload["plans"]}
        first = rows[self.plan.id]
        self.assertIn("blocked work", first["reasons"])
        self.assertIn("stale claim", first["reasons"])
        self.assertEqual(first["task_counts"]["doing"], 2)
        second = rows[self.second.id]
        self.assertEqual(second["approval"]["revision"], 1)
        self.assertEqual(second["approval"]["drift"], 1)
        self.assertEqual(second["question_count"], 1)
        self.assertIn("drift", second["reasons"])
        self.assertIn("open questions", second["reasons"])
        self.assertEqual(payload["counts"]["open_questions"], 1)
        self.assertEqual(payload["counts"]["drift"], 1)
        self.assertEqual(payload["needs_me_plan_ids"], sorted([self.plan.id, self.second.id]))

    def test_claims_and_overlaps(self) -> None:
        payload = self._build()
        self.assertNotIn("agents", payload)
        self.assertEqual(payload["counts"]["claims"], 2)
        self.assertEqual(len(payload["claims"]), 2)
        self.assertEqual(payload["counts"]["overlaps"], 1)
        self.assertEqual(
            payload["overlaps"][0]["task_ids"],
            sorted([self.tasks["overlap-a"], self.tasks["overlap-b"]]),
        )
        self.assertEqual(payload["overlaps"][0]["patterns"], ["src/app", "src/app/api.py"])

    def test_plan_scope_limits_the_payload(self) -> None:
        payload = self._build(plan_id=self.second.id)
        self.assertEqual([row["id"] for row in payload["plans"]], [self.second.id])
        self.assertEqual(payload["attention"], [])
        self.assertEqual(payload["claims"], [])
        self.assertEqual(payload["overlaps"], [])
        self.assertEqual(payload["counts"]["plans"], 1)

    def test_limits_keep_the_payload_bounded(self) -> None:
        payload = self._build(max_attention=2, max_plans=1, max_claims=1)
        self.assertEqual(len(payload["attention"]), 2)
        self.assertEqual(len(payload["plans"]), 1)
        self.assertEqual(len(payload["claims"]), 1)
        self.assertEqual(payload["counts"]["attention"], 6)
        self.assertEqual(payload["counts"]["claims"], 2)

    def test_attention_ids_still_match_the_reason_map(self) -> None:
        self.assertEqual(
            stats.attention_ids(self.store, now=NOW),
            set(stats.attention_reasons(self.store, now=NOW)),
        )


if __name__ == "__main__":
    unittest.main()
