"""End-to-end coverage for the Next horizon seams."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.services import evidence, questions, ready, review, revisions
from lazyplan.store import Store


class TestNextHorizon(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", "What", goal="Why", worktree_required=False)
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            "Approach: do it.\n\nCommit: one slice.\n\nVerify: pytest.",
        )
        self.criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(self.criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_approve_prove_question_ready_review_and_transfer(self) -> None:
        approval = revisions.approve(self.store, self.plan.id, reason="initial")
        self.assertTrue(approval.created)
        self.store.update_task(self.task.id, title="Renamed", reason="clarify")
        drift = revisions.diff(self.store, self.plan.id)
        self.assertTrue(drift.drifted)
        self.assertEqual(drift.entries[0].reason, "clarify")

        proof = evidence.prove(
            self.store, self.criterion.id, command="pytest", exit_code=0, task_id=self.task.id
        )
        self.assertFalse(proof.criterion.done)
        self.assertIsNone(evidence.task_gate(self.store, self.task.id))

        question = questions.add_question(self.store, self.plan.id, "Which host?")
        readiness = ready.check(self.store, self.plan.id)
        assert readiness is not None
        self.assertFalse(readiness.ready)
        questions.resolve_question(self.store, question.id, "OpenCode", actor="human")
        readiness = ready.check(self.store, self.plan.id)
        assert readiness is not None
        self.assertTrue(readiness.ready)

        packet = review.build(self.store, self.plan.id, cwd=self.tmp.name)
        assert packet is not None
        self.assertIn("## Acceptance criteria", packet.markdown)
        self.assertEqual(packet.payload["criteria"][0]["evidence"], "pass")
        self.assertEqual(packet.payload["approval"]["revision"], 1)

        dump = services.export_all(self.store)
        self.assertEqual(dump["plans"][0]["criteria"][0]["evidence"][0]["command"], "pytest")
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["evidence"], 1)
            self.assertEqual(counts["plans"], 1)
            target_plan = target.list_plans()[0]
            self.assertEqual(
                target.list_questions(target_plan.id, status="all")[0].text, "Which host?"
            )
            imported = review.build(target, target_plan.id, cwd=other)
            assert imported is not None
            self.assertEqual(imported.payload["criteria"][0]["evidence"], "pass")
            self.assertEqual(imported.payload["approval"]["revision"], 0)


if __name__ == "__main__":
    unittest.main()
