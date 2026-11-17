"""Pure planning rules: rollup, transitions, archiving, and progress."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Plan, Status, Task
from lazyplan.core.policies.planning import (
    ARCHIVE_AFTER_SECS,
    is_archived,
    next_status,
    progress_counts,
    rollup_target,
)


class TestRollup(unittest.TestCase):
    def test_rollup_target_matrix(self) -> None:
        cases = (
            ((), Status.TODO),
            ((Status.DONE, Status.DONE), Status.DONE),
            ((Status.TODO, Status.DOING, Status.DONE), Status.DOING),
            ((Status.TODO, Status.DONE), Status.TODO),
        )
        for statuses, expected in cases:
            with self.subTest(statuses=statuses):
                self.assertEqual(rollup_target(list(statuses)), expected)


class TestProgress(unittest.TestCase):
    def test_progress_counts_matrix(self) -> None:
        cases = (
            ([], (0, 0)),
            (
                [
                    Task(1, 1, "A", Status.TODO),
                    Task(2, 1, "B", Status.DOING),
                    Task(3, 1, "C", Status.DONE),
                    Task(4, 1, "D", Status.DONE),
                ],
                (2, 4),
            ),
        )
        for tasks, expected in cases:
            with self.subTest(tasks=len(tasks)):
                self.assertEqual(progress_counts(tasks), expected)
        self.assertEqual(
            progress_counts([Task(1, 1, "A", Status.DONE), Task(2, 1, "B", Status.TODO)]), (1, 2)
        )


class TestTransitions(unittest.TestCase):
    def test_cycle(self) -> None:
        self.assertEqual(next_status(Status.TODO), Status.DOING)
        self.assertEqual(next_status(Status.DOING), Status.DONE)
        self.assertEqual(next_status(Status.DONE), Status.TODO)


class TestArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = Plan(id=1, name="P", status=Status.DONE)

    def test_archive_matrix(self) -> None:
        cases = (
            (
                "past window",
                Status.DONE,
                {1: (100.0, Status.DONE.value)},
                100.0 + ARCHIVE_AFTER_SECS + 1,
                True,
            ),
            (
                "inside window",
                Status.DONE,
                {1: (100.0, Status.DONE.value)},
                100.0 + ARCHIVE_AFTER_SECS - 1,
                False,
            ),
            ("missing history", Status.DONE, {}, 10_000.0, False),
            ("open plan", Status.DOING, {1: (100.0, Status.DOING.value)}, 10_000.0, False),
        )
        for label, status, events, now, expected in cases:
            with self.subTest(case=label):
                self.plan.status = status
                self.assertEqual(is_archived(self.plan, events, now), expected)


if __name__ == "__main__":
    unittest.main()
