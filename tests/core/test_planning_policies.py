"""Pure planning rules: rollup, transitions, archiving, and progress."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Criterion, Plan, Status
from lazyplan.core.policies.planning import (
    ARCHIVE_AFTER_SECS,
    criterion_progress,
    is_archived,
    next_status,
    rollup_target,
)


class TestRollup(unittest.TestCase):
    def test_empty_is_todo(self) -> None:
        self.assertEqual(rollup_target([]), Status.TODO)

    def test_all_done_is_done(self) -> None:
        self.assertEqual(rollup_target([Status.DONE, Status.DONE]), Status.DONE)

    def test_any_doing_is_doing(self) -> None:
        self.assertEqual(rollup_target([Status.TODO, Status.DOING, Status.DONE]), Status.DOING)

    def test_otherwise_todo(self) -> None:
        self.assertEqual(rollup_target([Status.TODO, Status.DONE]), Status.TODO)


class TestTransitions(unittest.TestCase):
    def test_cycle(self) -> None:
        self.assertEqual(next_status(Status.TODO), Status.DOING)
        self.assertEqual(next_status(Status.DOING), Status.DONE)
        self.assertEqual(next_status(Status.DONE), Status.TODO)


class TestArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = Plan(id=1, name="P", status=Status.DONE)

    def test_done_past_window_is_archived(self) -> None:
        events = {1: (100.0, Status.DONE.value)}
        self.assertTrue(is_archived(self.plan, events, 100.0 + ARCHIVE_AFTER_SECS + 1))

    def test_done_inside_window_is_visible(self) -> None:
        events = {1: (100.0, Status.DONE.value)}
        self.assertFalse(is_archived(self.plan, events, 100.0 + ARCHIVE_AFTER_SECS - 1))

    def test_missing_history_never_hides(self) -> None:
        self.assertFalse(is_archived(self.plan, {}, 10_000.0))

    def test_open_plan_is_never_archived(self) -> None:
        self.plan.status = Status.DOING
        events = {1: (100.0, Status.DOING.value)}
        self.assertFalse(is_archived(self.plan, events, 10_000.0))


class TestCriterionProgress(unittest.TestCase):
    def test_counts_done_and_total(self) -> None:
        items = [
            Criterion(id=1, parent_kind="plan", parent_id=1, text="a", done=True),
            Criterion(id=2, parent_kind="plan", parent_id=1, text="b"),
        ]
        self.assertEqual(criterion_progress(items), (1, 2))

    def test_empty_checklist(self) -> None:
        self.assertEqual(criterion_progress([]), (0, 0))


if __name__ == "__main__":
    unittest.main()
