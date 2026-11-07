"""Pure plan-question rules."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import PlanQuestion
from lazyplan.core.policies.questions import (
    open_count,
    open_questions,
    validate_status,
    validate_text,
)


def question(qid: int = 1, status: str = "open") -> PlanQuestion:
    return PlanQuestion(id=qid, plan_id=1, text="Why?", status=status)


class TestQuestionPolicy(unittest.TestCase):
    def test_text_is_trimmed_and_required(self) -> None:
        self.assertEqual(validate_text("  Why?  "), "Why?")
        with self.assertRaises(ValueError):
            validate_text("   ")

    def test_status_is_open_or_resolved(self) -> None:
        self.assertEqual(validate_status("open"), "open")
        self.assertEqual(validate_status("resolved"), "resolved")
        with self.assertRaises(ValueError):
            validate_status("closed")

    def test_entity_rejects_empty_text_and_bad_status(self) -> None:
        with self.assertRaises(ValueError):
            PlanQuestion(id=1, plan_id=1, text=" ")
        with self.assertRaises(ValueError):
            PlanQuestion(id=1, plan_id=1, text="Why?", status="closed")

    def test_open_subset_and_count(self) -> None:
        rows = [question(1), question(2, "resolved"), question(3)]
        self.assertEqual([row.id for row in open_questions(rows)], [1, 3])
        self.assertEqual(open_count(rows), 2)


if __name__ == "__main__":
    unittest.main()
