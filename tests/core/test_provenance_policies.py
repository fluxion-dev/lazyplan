"""Pure provenance rules: trailers, branches, and forge state."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.provenance import (
    branch_ref,
    checks_state,
    letter_for_kind,
    pr_state,
    trailer_refs,
)


class TestTrailers(unittest.TestCase):
    def test_multiple_refs_are_sorted(self) -> None:
        message = "Work\n\nLazyplan: T12, M3\nLazyplan: P1"
        self.assertEqual(trailer_refs(message), [("milestone", 3), ("plan", 1), ("task", 12)])

    def test_no_trailer(self) -> None:
        self.assertEqual(trailer_refs("plain commit"), [])


class TestBranches(unittest.TestCase):
    def test_task_branch(self) -> None:
        self.assertEqual(branch_ref("task/12-slug"), ("task", 12))

    def test_non_task_branch(self) -> None:
        self.assertIsNone(branch_ref("feature/thing"))

    def test_letter(self) -> None:
        self.assertEqual(letter_for_kind("task"), "T")


class TestForgeState(unittest.TestCase):
    def test_merged_wins(self) -> None:
        self.assertEqual(pr_state({"state": "closed", "merged_at": "2026-01-01"}), "merged")

    def test_draft(self) -> None:
        self.assertEqual(pr_state({"state": "open", "draft": True}), "draft")

    def test_checks_pass(self) -> None:
        data = {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        self.assertEqual(checks_state(data), "pass")

    def test_checks_pending_and_fail(self) -> None:
        pending = {"check_runs": [{"status": "queued", "conclusion": ""}]}
        failure = {"check_runs": [{"status": "completed", "conclusion": "failure"}]}
        self.assertEqual(checks_state(pending), "pending")
        self.assertEqual(checks_state(failure), "fail")
        self.assertEqual(checks_state(None), "none")


if __name__ == "__main__":
    unittest.main()
