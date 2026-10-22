"""Read-first detail: safe browsing, explicit edit mode, and row actions."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.screens import (
        ConfirmScreen,
        DetailScreen,
        FilterPromptScreen,
        NewMilestoneScreen,
        NewTaskScreen,
    )
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestDetailScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("Plan title", "What we build", goal="Why we build").id
        self.sid = store.add_milestone(self.pid, "Milestone title", "Milestone details").id
        self.tid = store.add_task(self.sid, "Task title", "Task details").id
        store.add_criteria("plan", self.pid, "Criterion one")
        store.add_criteria("plan", self.pid, "Criterion two")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _open(self, pilot, kind: str, oid: int) -> None:
        self.app.selected = (kind, oid)
        await pilot.press("enter")
        await pilot.pause()

    async def test_read_mode_shows_context_without_inputs(self):
        from textual.widgets import Static

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            screen = self.app.screen
            self.assertIsInstance(screen, DetailScreen)
            body = str(screen.query_one("#detail-body", Static).render())
            self.assertIn("Why we build", body)
            self.assertIn("What we build", body)
            self.assertIn("Criterion one", body)
            self.assertIn("M", body)
            self.assertIn("Milestone title", body)
            self.assertFalse(screen.query_one("#detail-edit").display)
            self.assertTrue(screen.query_one("#detail-read").display)

    async def test_e_edits_and_saves(self):
        from textual.widgets import Input

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("e")
            await pilot.pause()
            self.assertTrue(self.app.screen.query_one("#detail-edit").display)
            self.app.screen.query_one("#d-title", Input).value = "Plan renamed"
            await pilot.press("ctrl+s")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_plan(self.pid).name, "Plan renamed")
            self.assertFalse(self.app.screen.query_one("#detail-edit").display)

    async def test_dirty_escape_prompts_and_cancel_keeps_detail(self):
        from textual.widgets import Input

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("e")
            await pilot.pause()
            self.app.screen.query_one("#d-title", Input).value = "dirty"
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(Store(self.db).get_task(self.tid).title, "Task title")

    async def test_a_adds_criterion_and_x_ticks(self):
        from textual.widgets import Static

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            from textual.widgets import Input

            self.app.screen.query_one("#filter-input", Input).value = "Task works"
            await pilot.press("enter")
            await pilot.pause()
            criteria = Store(self.db).list_criteria("task", self.tid)
            self.assertEqual(len(criteria), 1)
            self.assertIn(
                "Task works", str(self.app.screen.query_one("#detail-body", Static).render())
            )
            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(Store(self.db).list_criteria("task", self.tid)[0].done)

    async def test_n_adds_child_by_kind(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, NewMilestoneScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await self._open(pilot, "milestone", self.sid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, NewTaskScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_delete_confirms_cascade_and_cancel_keeps_row(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            text = self.app.screen.text
            self.assertIn("Plan title", text)
            self.assertIn("1 milestones", text)
            self.assertIn("1 tasks", text)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsNotNone(Store(self.db).get_plan(self.pid))

    async def test_delete_enter_defaults_to_cancel(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertIsNotNone(Store(self.db).get_plan(self.pid))

    async def test_detail_fits_80x24(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            page = self.app.screen.query_one("#detail-page")
            region = page.region
            self.assertLessEqual(region.x + region.width, 80)
            self.assertLessEqual(region.y + region.height, 24)


if __name__ == "__main__":
    unittest.main()
