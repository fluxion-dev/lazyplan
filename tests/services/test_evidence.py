"""Evidence use cases: prove a criterion, gate a task, and report coverage."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import evidence, tasks
from lazyplan.services.base import GateError
from lazyplan.store import Store


class TestEvidenceService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")
        self.criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.relate_criterion(self.criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_passing_proof_records_without_completing(self) -> None:
        result = evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=0)
        self.assertTrue(result.evidence.passing)
        self.assertFalse(result.criterion.done)
        self.assertFalse(self.store.get_criterion(self.criterion.id).done)

    def test_failing_proof_leaves_open(self) -> None:
        result = evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=1)
        self.assertFalse(result.criterion.done)
        self.assertFalse(result.evidence.passing)

    def test_completion_is_a_separate_edit(self) -> None:
        evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=0)
        self.assertFalse(self.store.get_criterion(self.criterion.id).done)
        self.store.update_criterion(self.criterion.id, done=True)
        self.assertTrue(self.store.get_criterion(self.criterion.id).done)
        self.assertEqual(len(evidence.list_evidence(self.store, self.criterion.id)), 1)

    def test_task_gate_requires_the_latest_pass(self) -> None:
        self.assertIsNotNone(evidence.task_gate(self.store, self.task.id))
        evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=0)
        self.assertIsNone(evidence.task_gate(self.store, self.task.id))
        evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=1)
        failure = evidence.task_gate(self.store, self.task.id)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertIn(f"#{self.criterion.id}", failure)

    def test_finish_gate_runs_before_branch_checks(self) -> None:
        with self.assertRaises(GateError):
            tasks.finish_task(self.store, self.task.id, require_evidence=True)
        evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=0)
        with self.assertRaises(ValueError):
            tasks.finish_task(self.store, self.task.id, require_evidence=True)

    def test_finish_gate_override_still_needs_a_branch(self) -> None:
        with self.assertRaises(ValueError):
            tasks.finish_task(
                self.store,
                self.task.id,
                require_evidence=True,
                override="accepted by human",
            )

    def test_coverage_counts_plan_tree(self) -> None:
        extra = self.store.add_criteria("plan", self.plan.id, "Ships")
        evidence.prove(self.store, self.criterion.id, command="pytest", exit_code=0)
        self.assertEqual(evidence.coverage(self.store, [self.plan.id]), (1, 2))
        evidence.prove(self.store, extra.id, note="reviewed")
        self.assertEqual(evidence.coverage(self.store, [self.plan.id]), (2, 2))

    def test_missing_criterion_raises(self) -> None:
        with self.assertRaises(KeyError):
            evidence.prove(self.store, 999_999, command="pytest")


if __name__ == "__main__":
    unittest.main()
