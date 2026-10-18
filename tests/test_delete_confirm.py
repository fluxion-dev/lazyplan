"""Destructive `: ` verbs confirm first; confirm dialogs render centered.

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
    from lazyplan.screens import ConfirmScreen
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestDeleteConfirm(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_project("P").id
        self.sid = store.add_story(self.pid, "S").id
        self.tid = store.add_task(self.sid, "T").id
        self.lid = store.add_link("task", self.tid, "https://x.example").id
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _submit(self, pilot, text):
        from textual.widgets import Input

        bar = self.app.query_one("#cmdbar", Input)
        bar.focus()
        bar.value = text
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_cmdbar_delete_asks_first(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._submit(pilot, f"delete --kind task --id {self.tid}")
            self.assertEqual(len(self.app.screen_stack), 2)
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            # cancel: row survives
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertIsNotNone(Store(self.db).get_task(self.tid))
            # confirm: row goes
            await self._submit(pilot, f"delete --kind task --id {self.tid}")
            await pilot.click("#ok")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertIsNone(Store(self.db).get_task(self.tid))

    async def test_cmdbar_delete_link_confirms(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._submit(pilot, f"delete-link --id {self.lid}")
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(Store(self.db).list_links("task", self.tid)), 1)

    async def test_cmdbar_status_runs_without_confirm(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await self._submit(pilot, f"status --kind task --id {self.tid} --to doing")
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(Store(self.db).get_task(self.tid).status.value, "doing")

    async def test_confirm_dialog_centered(self):
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.app.push_screen(ConfirmScreen("Delete task #1?"))
            await pilot.pause()
            dlg = self.app.screen.query_one("#dlg")
            region = dlg.region
            self.assertAlmostEqual(region.x, (100 - region.width) / 2, delta=1, msg=f"dlg {region}")
            self.assertAlmostEqual(region.y, (30 - region.height) / 2, delta=1, msg=f"dlg {region}")


if __name__ == "__main__":
    unittest.main()
