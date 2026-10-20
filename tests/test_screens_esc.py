"""Esc backs out of every modal form without saving.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
"""

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
        HelpScreen,
        NewTaskScreen,
        ProjectEditorScreen,
    )
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestEscBacksOut(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("P").id
        self.sid = store.add_milestone(self.pid, "S").id
        self.tid = store.add_task(self.sid, "T").id
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _esc_out(self, pilot, screen):
        self.app.push_screen(screen)
        await pilot.pause()
        self.assertGreater(len(self.app.screen_stack), 1)
        await pilot.press("escape")
        await pilot.pause()
        self.assertEqual(len(self.app.screen_stack), 1)

    async def test_editor_esc_discards_clean(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.push_screen(ProjectEditorScreen(Store(self.db), self.pid))
            await pilot.pause()
            self.assertGreater(len(self.app.screen_stack), 1)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(Store(self.db).get_task(self.tid).title, "T")

    async def test_editor_esc_dirty_prompts_then_discards(self):
        from textual.widgets import Input

        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.push_screen(ProjectEditorScreen(Store(self.db), self.pid))
            await pilot.pause()
            self.app.screen.query_one("#p-title", Input).value = "CHANGED"
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.click("#ok")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(Store(self.db).get_plan(self.pid).name, "P")

    async def test_detail_esc_discards_textarea(self):
        from textual.widgets import TextArea

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._esc_out(pilot, DetailScreen(Store(self.db), "task", self.tid))
            # focused TextArea variant: edits must not leak either
            self.app.push_screen(DetailScreen(Store(self.db), "task", self.tid))
            await pilot.pause()
            self.app.screen.query_one("#d-desc", TextArea).focus()
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(Store(self.db).get_task(self.tid).description, "")

    async def test_new_task_esc_creates_nothing(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            before = len(Store(self.db).list_tasks(self.sid))
            await self._esc_out(pilot, NewTaskScreen(self.sid))
            self.assertEqual(len(Store(self.db).list_tasks(self.sid)), before)

    async def test_confirm_esc_does_not_delete(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._esc_out(pilot, ConfirmScreen("Delete task?"))
            self.assertIsNotNone(Store(self.db).get_task(self.tid))

    async def test_help_esc(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._esc_out(pilot, HelpScreen())


if __name__ == "__main__":
    unittest.main()
