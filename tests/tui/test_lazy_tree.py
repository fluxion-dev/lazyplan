"""Lazy plan tree: collapsed branches do not materialize child nodes."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from textual.widgets import Tree

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.state import PlanMode
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]
    PlanMode = None  # type: ignore[assignment]


@unittest.skipUnless(
    tui_mod is not None and getattr(tui_mod, "_TEXTUAL_OK", False), "textual not installed"
)
class LazyTreeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "lazy.db")
        store = Store(self.db)
        self.plan_a = store.add_plan("Alpha", "What", goal="Why")
        self.plan_b = store.add_plan("Beta", "What", goal="Why")
        self.milestone_a = store.add_milestone(self.plan_a.id, "Alpha milestone", "Slice")
        self.milestone_b = store.add_milestone(self.plan_b.id, "Beta milestone", "Slice")
        self.task_a = store.add_task(self.milestone_a.id, "Visible task", "Unit")
        self.task_b = store.add_task(self.milestone_b.id, "Hidden match", "Unit")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _app(self):
        return tui_mod.create_app(self.db, startup_mode=PlanMode.BOTH)

    async def test_first_paint_materializes_only_plans(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.assertEqual(
                set(app._row_nodes), {("plan", self.plan_a.id), ("plan", self.plan_b.id)}
            )
            tree = app.query_one("#tree", Tree)
            self.assertEqual(len(tree.root.children), 2)

    async def test_expanding_a_plan_loads_only_its_milestones(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            tree = app.query_one("#tree", Tree)
            tree.move_cursor(app._row_nodes[("plan", self.plan_a.id)])
            await pilot.pause()
            await pilot.press("right")
            await settle(pilot)
            self.assertIn(("milestone", self.milestone_a.id), app._row_nodes)
            self.assertNotIn(("milestone", self.milestone_b.id), app._row_nodes)
            self.assertNotIn(("task", self.task_a.id), app._row_nodes)

    async def test_expanding_a_milestone_loads_its_tasks(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.tree_controller.load_children(("plan", self.plan_a.id))
            app._expanded.add(("plan", self.plan_a.id))
            app._row_nodes[("plan", self.plan_a.id)].expand()
            app.tree_controller.load_children(("milestone", self.milestone_a.id))
            self.assertIn(("task", self.task_a.id), app._row_nodes)
            self.assertIn(("milestone", self.milestone_a.id), app._row_nodes)

    async def test_filter_reveals_a_collapsed_match(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.filter_text = "hidden match"
            app.refresh_all()
            await settle(pilot)
            self.assertIn(("task", self.task_b.id), app._row_nodes)
            self.assertNotIn(("task", self.task_a.id), app._row_nodes)
            self.assertIn(("milestone", self.milestone_b.id), app._row_nodes)

    async def test_refresh_restores_the_selected_task_path(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.tree_controller.expand_all()
            app.selected = ("task", self.task_a.id)
            app.refresh_all()
            await settle(pilot)
            self.assertIn(("task", self.task_a.id), app._row_nodes)
            self.assertEqual(app.selected, ("task", self.task_a.id))
            self.assertIn(("plan", self.plan_a.id), app._expanded)
            self.assertIn(("milestone", self.milestone_a.id), app._expanded)

    async def test_mode_scopes_which_plans_materialize(self) -> None:
        self.store.set_status_raw("plan", self.plan_b.id, Status.DONE)
        active = tui_mod.create_app(self.db, startup_mode=PlanMode.ACTIVE)
        async with active.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.assertIn(("plan", self.plan_a.id), active._row_nodes)
            self.assertNotIn(("plan", self.plan_b.id), active._row_nodes)
        finished = tui_mod.create_app(self.db, startup_mode=PlanMode.FINISHED)
        async with finished.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.assertNotIn(("plan", self.plan_a.id), finished._row_nodes)
            self.assertIn(("plan", self.plan_b.id), finished._row_nodes)

    async def test_fold_all_loads_only_visible_branches(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.tree_controller.fold_all()
            await settle(pilot)
            self.assertIn(("milestone", self.milestone_a.id), app._row_nodes)
            self.assertIn(("milestone", self.milestone_b.id), app._row_nodes)
            self.assertIn(("task", self.task_a.id), app._row_nodes)
            self.assertIn(("task", self.task_b.id), app._row_nodes)


if __name__ == "__main__":
    unittest.main()
