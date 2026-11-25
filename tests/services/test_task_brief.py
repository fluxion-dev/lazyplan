"""Fresh task briefs: content, budget, and fresh-session instructions."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import task_brief
from lazyplan.store import Store

TASK_DESC = (
    "Approach: Change the scouted path and keep the reviewed behavior.\n\n"
    "Touch: src/app.py, tests/test_app.py\n\n"
    "Inputs: The approved definition.\n\n"
    "Commit: One implementation slice.\n\n"
    "Verify: The relevant test suite passes.\n\n"
    "Guardrails: Keep unrelated behavior unchanged."
)


class TaskBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        self.plan = self.store.add_plan("Plan", "the what", goal="the why")
        self.milestone = self.store.add_milestone(
            self.plan.id,
            "Milestone",
            (
                "Outcome: As a user, I want the slice.\n\n"
                "Scope: In scope: the slice.\n\n"
                "Inputs: The approved definition.\n\n"
                "Slices: Implement and verify."
            ),
        )
        self.previous = self.store.add_task(self.milestone.id, "Previous task", "Done already.")
        self.task = self.store.add_task(self.milestone.id, "Current task", TASK_DESC)
        self.store.add_touchpoint(self.task.id, "src/app.py")
        self.store.add_criteria("task", self.task.id, "Tests pass")
        self.store.add_question(self.plan.id, "Which host?")
        self.store.add_note("task", self.task.id, "Decision: keep it small")
        self.store.add_comment("task", self.task.id, "Please check the edge case")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_brief_is_self_contained_and_fits(self) -> None:
        brief = task_brief.build(self.store, self.task.id, window=128_000)
        self.assertTrue(brief.fits)
        self.assertLess(brief.tokens, brief.budget)
        self.assertIn("Start a new session for this task", brief.text)
        self.assertIn("Do not continue another task's conversation", brief.text)
        self.assertIn("## Plan P1: Plan", brief.text)
        self.assertIn("## Milestone M1: Milestone", brief.text)
        self.assertIn("## Task T2: Current task", brief.text)
        self.assertIn("Approach: Change the scouted path", brief.text)
        self.assertIn("src/app.py", brief.text)
        self.assertIn("Previous task: T1 Previous task (todo)", brief.text)
        self.assertIn("Open question Q1: Which host?", brief.text)
        self.assertIn("Decision: keep it small", brief.text)
        self.assertIn("Please check the edge case", brief.text)
        self.assertIn("Session budget:", brief.text)
        self.assertIn("End the session.", brief.text)

    def test_oversize_brief_is_refused(self) -> None:
        self.store.update_task(self.task.id, description="x" * 6000)
        brief = task_brief.build(self.store, self.task.id, window=1000)
        self.assertFalse(brief.fits)
        self.assertGreater(brief.tokens, brief.budget)
        with self.assertRaisesRegex(task_brief.ContextBudgetError, "fresh brief uses"):
            brief.require_fits()

    def test_extra_commands_are_measured_and_included(self) -> None:
        brief = task_brief.build(
            self.store,
            self.task.id,
            window=128_000,
            extra="claim T2\nlink the commit",
        )
        self.assertIn("## Session commands", brief.text)
        self.assertIn("claim T2", brief.text)
        tight = task_brief.build(
            self.store,
            self.task.id,
            window=1000,
            extra="x" * 2000,
        )
        self.assertFalse(tight.fits)

    def test_invalid_window_and_percent_are_rejected(self) -> None:
        for window in (0, -1, True):
            with self.subTest(window=window), self.assertRaisesRegex(ValueError, "context window"):
                task_brief.build(self.store, self.task.id, window=window)
        for percent in (0, 101, True):
            with (
                self.subTest(percent=percent),
                self.assertRaisesRegex(ValueError, "context percent"),
            ):
                task_brief.build(self.store, self.task.id, window=128_000, percent=percent)

    def test_missing_task_is_named(self) -> None:
        with self.assertRaisesRegex(KeyError, "task #999"):
            task_brief.build(self.store, 999, window=128_000)


if __name__ == "__main__":
    unittest.main()
