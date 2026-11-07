"""Plan readiness checks: lint, criterion coverage, and questions."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import ready
from lazyplan.store import Store


class TestReadyService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            "Approach: do it.\n\nCommit: one slice.\n\nVerify: pytest.",
        )
        criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_plan_is_ready(self) -> None:
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        self.assertTrue(result.ready)
        self.assertEqual([check.id for check in result.checks], ["lint", "coverage", "questions"])
        self.assertTrue(all(check.ok for check in result.checks))

    def test_lint_failure(self) -> None:
        self.store.add_task(self.milestone.id, "Vague", "TODO: fix")
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        lint_check = next(check for check in result.checks if check.id == "lint")
        self.assertFalse(lint_check.ok)
        self.assertFalse(result.ready)

    def test_coverage_failure(self) -> None:
        self.store.add_criteria("plan", self.plan.id, "Unproven")
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        coverage = next(check for check in result.checks if check.id == "coverage")
        self.assertFalse(coverage.ok)
        self.assertIn("1/2", coverage.detail)
        self.assertEqual(len(coverage.findings), 1)

    def test_open_question_failure(self) -> None:
        question = self.store.add_question(self.plan.id, "Which host?")
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        questions = next(check for check in result.checks if check.id == "questions")
        self.assertFalse(questions.ok)
        self.assertEqual(questions.findings[0]["id"], question.id)
        self.assertFalse(result.ready)

    def test_missing_plan_is_none(self) -> None:
        self.assertIsNone(ready.check(self.store, 999_999))

    def test_check_does_not_write(self) -> None:
        before = self.store.path.read_bytes()
        ready.check(self.store, self.plan.id)
        self.assertEqual(self.store.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
