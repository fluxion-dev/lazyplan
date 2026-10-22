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
        self.pid = store.add_plan("P").id
        self.sid = store.add_milestone(self.pid, "S").id
        self.tid = store.add_task(self.sid, "T").id
        self.bare_tid = store.add_task(self.sid, "Bare").id
        self.sha = "a" * 40
        store.link_commit("task", self.tid, self.sha, subject="work")
        store.link_commit("plan", self.pid, "b" * 40)
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_linked_rows_stay_clean_and_preview_counts(self):
        from textual.widgets import Static, Tree

        async with self.app.run_test() as pilot:
            await pilot.pause()
            task_label = str(self.app._row_nodes[("task", self.tid)].label)
            self.assertNotIn(self.sha[:12], task_label)
            plan_label = str(self.app._row_nodes[("plan", self.pid)].label)
            self.assertNotIn("b" * 12, plan_label)
            tree = self.app.query_one("#tree", Tree)
            tree.move_cursor(self.app._row_nodes[("task", self.tid)])
            await pilot.pause()
            preview = str(self.app.query_one("#preview-body", Static).render())
            self.assertIn("1 commits", preview)

    async def test_detail_lists_commits(self):
        from textual.widgets import Static

        from lazyplan.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.selected = ("task", self.tid)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn(self.sha[:12], body)
            self.assertIn("work", body)

    async def test_detail_hides_empty_commits(self):
        from textual.widgets import Static

        from lazyplan.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.selected = ("task", self.bare_tid)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertNotIn("commits", body)


if __name__ == "__main__":
    unittest.main()
