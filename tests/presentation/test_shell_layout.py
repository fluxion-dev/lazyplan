"""The left column hides empty panes; the overview keeps its height."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


EXPECTED_LEFT = ("plans-active", "agents", "plans-finished", "git")
EXPECTED_RIGHT = ("preview",)


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestShellLayout(unittest.IsolatedAsyncioTestCase):
    def _store(self) -> Store:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        return Store(os.path.join(self.tmp.name, "layout.db"))

    async def test_wide_shell_hides_empty_panes_and_fills_the_overview(self) -> None:
        store = self._store()
        plan = store.add_plan("Plan", "What", goal="Why")
        milestone = store.add_milestone(plan.id, "Milestone", "Details")
        store.add_task(milestone.id, "Task", "Details")
        app = create_app(str(store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            left = app.query_one("#left")
            side = app.query_one("#side")
            self.assertEqual(tuple(child.id for child in left.children), EXPECTED_LEFT)
            self.assertEqual(tuple(child.id for child in side.children), EXPECTED_RIGHT)
            self.assertTrue(side.display)
            self.assertLessEqual(abs(left.size.width - side.size.width), 1)
            self.assertTrue(app.query_one("#plans-active").display)
            self.assertFalse(app.query_one("#plans-finished").display)
            self.assertFalse(app.query_one("#agents").display)
            self.assertFalse(app.query_one("#git").display)
            preview = app.query_one("#preview")
            self.assertGreater(preview.size.height, 0)
            self.assertGreaterEqual(preview.size.height, side.size.height - 2)

    async def test_panes_return_when_they_have_rows(self) -> None:
        store = self._store()
        plan = store.add_plan("Plan", "What", goal="Why")
        store.add_milestone(plan.id, "Milestone", "Details")
        done = store.add_plan("Finished", "What", goal="Why")
        milestone = store.add_milestone(done.id, "Done slice", "Details")
        task = store.add_task(milestone.id, "Done task", "Details")
        store.set_status_raw("task", task.id, Status.DONE)
        store.set_status_raw("milestone", milestone.id, Status.DONE)
        store.set_status_raw("plan", done.id, Status.DONE)
        store.add_repo_link("plan", plan.id, "/home/u/checkouts/api", "git@github.com:org/api.git")
        store.add_agent(
            "ana",
            host="opencode",
            agent="ana",
            plan_id=plan.id,
            worktree=store.checkout_path(),
        )
        app = create_app(str(store.path))
        async with app.run_test(size=(130, 40)) as pilot:
            await pilot.pause()
            app.select_row("plan", plan.id)
            await pilot.pause()
            self.assertTrue(app.query_one("#plans-finished").display)
            self.assertTrue(app.query_one("#agents").display)
            self.assertTrue(app.query_one("#git").display)

    async def test_narrow_shell_stacks_the_same_cards_and_hides_the_side(self) -> None:
        store = self._store()
        plan = store.add_plan("Plan", "What", goal="Why")
        store.add_milestone(plan.id, "Milestone", "Details")
        app = create_app(str(store.path))
        async with app.run_test(size=(90, 40)) as pilot:
            await pilot.pause()
            left = app.query_one("#left")
            self.assertEqual(tuple(child.id for child in left.children), EXPECTED_LEFT)
            self.assertFalse(app.query_one("#side").display)
            self.assertFalse(app.query_one("#preview").display)


if __name__ == "__main__":
    unittest.main()
