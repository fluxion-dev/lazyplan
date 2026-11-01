"""Coordination use cases over the coordination port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.policies.coordination import parse_ttl
from lazyplan.store import Store


class TestCoordinationService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "coord.db"))
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.task = self.store.add_task(milestone.id, "T", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_suggest_selects_without_claiming(self) -> None:
        result = services.claim_next(self.store, "alice", suggest=True)
        assert result is not None
        self.assertIsNone(result["claim"])
        self.assertEqual(result["task"]["id"], self.task.id)
        self.assertIsNone(self.store.get_claim(self.task.id))

    def test_claim_moves_the_task_doing(self) -> None:
        result = services.start_claim(self.store, self.task.id, "alice", ttl="10m")
        self.assertEqual(result["claim"]["actor"], "alice")
        self.assertEqual(self.store.get_task(self.task.id).status.value, "doing")
        self.assertEqual(parse_ttl("10m"), 600)

    def test_block_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            services.block_task(self.store, self.task.id, "  ")


if __name__ == "__main__":
    unittest.main()
