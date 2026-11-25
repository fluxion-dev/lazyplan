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
        self.plan = self.store.add_plan("Plan", worktree_required=False)
        self.milestone = self.store.add_milestone(
            self.plan.id,
            "M",
            (
                "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
                "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
                "Inputs: The approved definition and the scouted code path.\n\n"
                "Slices: Implement and verify in separate green commits."
            ),
        )
        self.task = self.store.add_task(
            self.milestone.id,
            "T",
            (
                "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
                "Touch: src/app.py, tests/test_app.py\n\n"
                "Inputs: The approved definition; none beyond the plan scope.\n\n"
                "Commit: One implementation slice.\n\n"
                "Verify: The relevant test suite passes.\n\n"
                "Guardrails: Keep behavior outside the reviewed scope unchanged."
            ),
        )
        criterion = self.store.add_criteria("plan", self.plan.id, "Works")
        self.store.relate_criterion(criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_plan_is_ready(self) -> None:
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        self.assertTrue(result.ready)
        self.assertEqual(
            [check.id for check in result.checks],
            ["lint", "context", "coverage", "questions", "worktrees"],
        )
        self.assertTrue(all(check.ok for check in result.checks))

    def test_lint_failure(self) -> None:
        self.store.add_task(self.milestone.id, "Vague", "TODO: fix")
        result = ready.check(self.store, self.plan.id)
        assert result is not None
        lint_check = next(check for check in result.checks if check.id == "lint")
        self.assertFalse(lint_check.ok)
        self.assertFalse(result.ready)

    def test_context_failure(self) -> None:
        self.store.update_task(self.task.id, description="x" * 6000)
        result = ready.check(self.store, self.plan.id, context_windows={"implementer": 1000})
        assert result is not None
        context = next(check for check in result.checks if check.id == "context")
        self.assertFalse(context.ok)
        self.assertIn("tokens of a 250 budget", context.findings[0]["message"])
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
