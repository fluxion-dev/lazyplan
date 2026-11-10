"""Plan modes: Active, Finished, Both, full children, and no cap."""

from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui.controllers.filtering import TreeFilter
    from lazyplan.presentation.tui.state import PlanMode
except ImportError:  # pragma: no cover - stdlib-only interpreter
    TreeFilter = None  # type: ignore[assignment]
    PlanMode = None  # type: ignore[assignment]


@unittest.skipUnless(TreeFilter is not None, "textual not installed")
class TestPlanModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "modes.db"))
        self.open = self.store.add_plan("Open", actor="fixture")
        self.open_m = self.store.add_milestone(self.open.id, "M", actor="fixture")
        self.open_t = self.store.add_task(self.open_m.id, "T", actor="fixture")
        self.done = self.store.add_plan("Done", actor="fixture")
        done_m = self.store.add_milestone(self.done.id, "DM", actor="fixture")
        done_t = self.store.add_task(done_m.id, "DT", actor="fixture")
        services.set_status(self.store, "task", done_t.id, Status.DONE, actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def _tree(self, mode: PlanMode):
        app = SimpleNamespace(store=self.store, plan_mode=mode, filter_text="")
        return TreeFilter(app).filtered_tree()

    def test_active_keeps_open_plans_with_full_children(self):
        tree = self._tree(PlanMode.ACTIVE)
        self.assertEqual([plan.id for plan, _ in tree], [self.open.id])
        self.assertEqual(len(tree[0][1]), 1)
        self.assertEqual([task.id for _m, tasks in tree[0][1] for task in tasks], [self.open_t.id])

    def test_finished_keeps_done_plans(self):
        tree = self._tree(PlanMode.FINISHED)
        self.assertEqual([plan.id for plan, _ in tree], [self.done.id])

    def test_both_keeps_every_plan_and_sorts_done_last(self):
        tree = self._tree(PlanMode.BOTH)
        self.assertEqual([plan.id for plan, _ in tree], [self.open.id, self.done.id])

    def test_no_five_plan_cap(self):
        for index in range(7):
            self.store.add_plan(f"Extra {index}", actor="fixture")
        tree = self._tree(PlanMode.ACTIVE)
        self.assertEqual(len(tree), 8)
