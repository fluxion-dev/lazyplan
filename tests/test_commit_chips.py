"""Commit chips: linked rows show short-SHA chips, unlinked rows don't.

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
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestCommitChips(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_project("P").id
        self.sid = store.add_story(self.pid, "S").id
        self.tid = store.add_task(self.sid, "T").id
        self.bare_tid = store.add_task(self.sid, "Bare").id
        self.sha = "a" * 40
        store.link_commit("task", self.tid, self.sha, subject="work")
        store.link_commit("project", self.pid, "b" * 40)
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_linked_rows_show_chips(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            task_label = str(self.app._row_nodes[("task", self.tid)].label)
            self.assertIn(self.sha[:12], task_label)
            proj_label = str(self.app._row_nodes[("project", self.pid)].label)
            self.assertIn("b" * 12, proj_label)
            bare_label = str(self.app._row_nodes[("task", self.bare_tid)].label)
            self.assertNotIn(self.sha[:12], bare_label)
            self.assertNotIn("b" * 12, bare_label)

    async def test_refresh_prefetches_links_once(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            calls = []
            orig = self.app.store.links_map

            def counting():
                calls.append(1)
                return orig()

            self.app.store.links_map = counting  # type: ignore[method-assign]
            self.app.refresh_all("probe")
            await pilot.pause()
            self.assertEqual(len(calls), 1)

    async def test_detail_lists_commits(self):
        from textual.containers import Vertical
        from textual.widgets import Static, Tree

        from lazyplan.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("task", self.tid)])
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            box = self.app.screen.query_one("#d-commits", Vertical)
            self.assertTrue(box.display)
            text = "\n".join(str(s.render()) for s in box.query(Static))
            self.assertIn(self.sha[:12], text)
            self.assertIn("work", text)

    async def test_detail_hides_empty_commits(self):
        from textual.containers import Vertical
        from textual.widgets import Tree

        from lazyplan.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("task", self.bare_tid)])
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            box = self.app.screen.query_one("#d-commits", Vertical)
            self.assertFalse(box.display)


if __name__ == "__main__":
    unittest.main()
