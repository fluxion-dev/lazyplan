"""Review packet composition over a real store."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import build_review, review
from lazyplan.store import Store


class TestReviewService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", "What we build", goal="Why we build")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            "Approach: do it.\n\nCommit: one slice.\n\nVerify: pytest.",
        )
        criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(criterion.id, self.task.id)
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0, actor="ci")
        self.store.add_question(self.plan.id, "Which host?")
        self.store.add_revision(self.plan.id, "a" * 64, "{}", reason="initial")
        self.store.update_task(self.task.id, title="Renamed", reason="clarify")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_packet_contains_every_section(self) -> None:
        packet = build_review(self.store, self.plan.id, cwd=self.tmp.name)
        assert packet is not None
        self.assertEqual(packet.plan_id, self.plan.id)
        for section in (
            "## Why",
            "## What",
            "## Acceptance criteria",
            "## Milestones and tasks",
            "## Commits",
            "## Pull requests",
            "## Findings",
            "## Open questions",
        ):
            self.assertIn(section, packet.markdown)
        criterion = packet.payload["criteria"][0]
        self.assertEqual(criterion["evidence"], "pass")
        self.assertEqual(criterion["tasks"][0]["id"], self.task.id)
        self.assertEqual(packet.payload["questions"][0]["text"], "Which host?")
        self.assertEqual(packet.payload["approval"]["revision"], 1)
        self.assertEqual(packet.payload["approval"]["drift"], 1)

    def test_missing_plan_returns_none(self) -> None:
        self.assertIsNone(build_review(self.store, 999_999, cwd=self.tmp.name))

    def test_packet_is_deterministic(self) -> None:
        first = build_review(self.store, self.plan.id, cwd=self.tmp.name)
        second = build_review(self.store, self.plan.id, cwd=self.tmp.name)
        assert first is not None and second is not None
        self.assertEqual(first.markdown, second.markdown)

    def test_max_chars(self) -> None:
        packet = build_review(self.store, self.plan.id, max_chars=300, cwd=self.tmp.name)
        assert packet is not None
        self.assertLessEqual(len(packet.markdown), 300)

    def test_degraded_packet_without_approval_or_evidence(self) -> None:
        other = self.store.add_plan("Other")
        packet = review.build(self.store, other.id, cwd=self.tmp.name)
        assert packet is not None
        self.assertEqual(packet.payload["approval"]["revision"], 0)
        self.assertEqual(packet.payload["criteria"], [])
        self.assertIn("## Open questions", packet.markdown)


if __name__ == "__main__":
    unittest.main()
