"""Destructive palette commands confirm first; confirm dialogs render centered.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
Minimal keys own the tree; mutations run through the modal palette.
"""

import os
import tempfile
import unittest

from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from lazyplan import tui as tui_mod
    from lazyplan.screens import ConfirmScreen
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


async def _palette(pilot, query: str) -> None:
    """Drive the modal palette: open with c, type query, run first match."""
    await pilot.press("c")
    await pilot.pause()
    for ch in query:
        await pilot.press(ch)
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestDeleteConfirm(unittest.IsolatedAsyncioTestCase):
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

    async def test_d_key_delete_asks_first(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            await _palette(pilot, "delete")
            self.assertEqual(len(self.app.screen_stack), 2)
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            # cancel: row survives
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertIsNotNone(Store(self.db).get_task(self.tid))
            # confirm: row goes
            await _palette(pilot, "delete")
            await pilot.click("#ok")
            await pilot.pause()
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertIsNone(Store(self.db).get_task(self.tid))

    async def test_c_key_ticks_criteria(self):
        store = Store(self.db)
        cid = store.add_criteria("task", self.tid, "works").id
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            await _palette(pilot, "tick criteria")
            self.assertTrue(Store(self.db).list_criteria("task", self.tid)[0].done)
            await _palette(pilot, "tick criteria")  # nothing open: reopens the last one
            crit = Store(self.db).list_criteria("task", self.tid)[0]
            self.assertEqual(crit.id, cid)
            self.assertFalse(crit.done)

    async def test_space_runs_without_confirm(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            await pilot.press("space")
            await pilot.pause()
            # space is parked: nothing happens without the palette
            self.assertEqual(len(self.app.screen_stack), 1)
            self.assertEqual(Store(self.db).get_task(self.tid).status.value, "todo")
            await _palette(pilot, "cycle status")
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
