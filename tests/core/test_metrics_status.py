"""Status distribution: lifecycle counts and the blocked overlay."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store


class StatusDistributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.tasks = [self.store.add_task(self.milestone.id, f"T{n}") for n in range(4)]

    def _move(self, index: int, status: Status) -> None:
        services.set_status(self.store, "task", self.tasks[index].id, status, actor="qa")

    def test_counts_every_state(self) -> None:
        self._move(1, Status.DOING)
        self._move(2, Status.DONE)
        self._move(3, Status.DONE)
        status = metrics.status_distribution(self.store)
        self.assertEqual((status.todo, status.doing, status.done), (1, 1, 2))
        self.assertEqual(status.total, 4)

    def test_blocked_is_an_overlay(self) -> None:
        self._move(0, Status.DOING)
        self.store.set_blocked(self.tasks[0].id, True, "waiting", actor="qa")
        status = metrics.status_distribution(self.store)
        self.assertEqual(status.doing, 1)
        self.assertEqual(status.blocked, 1)
        self.assertEqual(status.total, 4)

    def test_shares_use_all_tasks(self) -> None:
        self._move(1, Status.DOING)
        self._move(2, Status.DONE)
        status = metrics.status_distribution(self.store)
        shares = [status.share(status.todo), status.share(status.doing), status.share(status.done)]
        self.assertEqual(shares, [50, 25, 25])
        self.assertEqual(sum(shares), 100)

    def test_empty_store_has_zero_rows(self) -> None:
        empty = Store(os.path.join(self.tmp.name, "empty.db"))
        status = metrics.status_distribution(empty)
        self.assertEqual(status.total, 0)
        self.assertEqual(status.share(0), 0)

    def test_snapshot_carries_status(self) -> None:
        snapshot = metrics.snapshot(self.store)
        self.assertIsNotNone(snapshot.status)
        self.assertEqual(snapshot.status.todo, 4)  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
