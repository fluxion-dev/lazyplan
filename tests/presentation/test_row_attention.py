"""Attention markers roll up from tasks and plan state."""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui.controllers.tree import TreeController
except ImportError:  # pragma: no cover - stdlib-only interpreter
    TreeController = None  # type: ignore[assignment]


@unittest.skipUnless(TreeController is not None, "textual not installed")
class TestRowAttention(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.tmp.name, "attention.db"))
        self.plan = self.store.add_plan("Plan", actor="fixture")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice", actor="fixture")
        self.task = self.store.add_task(self.milestone.id, "Task", actor="fixture")
        self.controller = TreeController(SimpleNamespace(store=self.store))
        self.base = services.tree(self.store, status=None, finished="show")

    def tearDown(self):
        self.tmp.cleanup()

    def _keys(self, reasons: dict[int, list[str]]) -> set[tuple[str, int]]:
        return self.controller._attention_keys(self.base, reasons)

    def test_blocked_marks_the_task_and_rolls_up(self):
        keys = self._keys({self.task.id: ["blocked"]})
        self.assertIn(("task", self.task.id), keys)
        self.assertIn(("milestone", self.milestone.id), keys)
        self.assertIn(("plan", self.plan.id), keys)

    def test_task_attention_rolls_up(self):
        keys = self._keys({self.task.id: ["failing checks"]})
        self.assertIn(("task", self.task.id), keys)
        self.assertIn(("milestone", self.milestone.id), keys)
        self.assertIn(("plan", self.plan.id), keys)

    def test_drift_marks_the_plan(self):
        self.controller._drift_map = {self.plan.id: 2}
        self.assertIn(("plan", self.plan.id), self._keys({}))

    def test_stale_source_marks_the_owning_row(self):
        self.controller._source_stats = {("task", self.task.id): (1, 0, 1, 0)}
        self.assertIn(("task", self.task.id), self._keys({}))

    def test_open_question_marks_the_plan(self):
        self.store.add_question(self.plan.id, "Which host?", actor="fixture")
        self.assertIn(("plan", self.plan.id), self._keys({}))

    def test_done_task_without_attention_stays_quiet(self):
        services.set_status(self.store, "task", self.task.id, Status.DONE, actor="fixture")
        self.assertEqual(self._keys({}), set())


if __name__ == "__main__":
    unittest.main()
