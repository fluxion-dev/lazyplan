"""The main shell splits plans into active and finished panels."""

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
except ImportError:  # pragma: no cover - stdlib-only interpreter
    TreeFilter = None  # type: ignore[assignment]


@unittest.skipUnless(TreeFilter is not None, "textual not installed")
class TestPlanSplit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "split.db"))
        self.open = self.store.add_plan("Open", actor="fixture")
        self.open_m = self.store.add_milestone(self.open.id, "M", actor="fixture")
        self.open_t = self.store.add_task(self.open_m.id, "T", actor="fixture")
        self.done = self.store.add_plan("Done", actor="fixture")
        done_m = self.store.add_milestone(self.done.id, "DM", actor="fixture")
        done_t = self.store.add_task(done_m.id, "DT", actor="fixture")
        services.set_status(self.store, "task", done_t.id, Status.DONE, actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def _split(self, filter_text: str = ""):
        app = SimpleNamespace(store=self.store, filter_text=filter_text)
        base = services.tree(self.store, status=None, archived="show")
        return TreeFilter(app).panels(base)

    def test_active_panel_keeps_open_plans_with_full_children(self):
        active, finished = self._split()
        self.assertEqual([plan.id for plan, _ in active], [self.open.id])
        self.assertEqual([plan.id for plan, _ in finished], [self.done.id])
        self.assertEqual(len(active[0][1]), 1)
        self.assertEqual(
            [task.id for _m, tasks in active[0][1] for task in tasks], [self.open_t.id]
        )

    def test_finished_panel_keeps_done_plans(self):
        _active, finished = self._split()
        self.assertEqual([plan.id for plan, _ in finished], [self.done.id])

    def test_text_filter_applies_inside_each_panel(self):
        active, finished = self._split(filter_text="open")
        self.assertEqual([plan.id for plan, _ in active], [self.open.id])
        self.assertEqual(finished, [])

    def test_no_five_plan_cap(self):
        for index in range(7):
            self.store.add_plan(f"Extra {index}", actor="fixture")
        active, _finished = self._split()
        self.assertEqual(len(active), 8)
