"""Commit chips: linked rows show short-SHA chips, unlinked rows don't.

Headless Textual pilot tests (skipped on stdlib-only interpreters).
"""

import os
import tempfile
import unittest

from lazyplan.store import Store
from tests.support.pilot import settle

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
        self.repo_tid = store.add_task(self.sid, "Repo only").id
        self.sha = "a" * 40
        store.link_commit("task", self.tid, self.sha, subject="work")
        store.link_commit("plan", self.pid, "b" * 40)
        store.add_repo_link("task", self.repo_tid, "/tmp/api", "git@github.com:org/api.git")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_compact_row_chips_and_preview_counts(self):
        from textual.widgets import Static

        async with self.app.run_test() as pilot:
            await pilot.pause()
            task_label = str(self.app._row_nodes[("task", self.tid)].label)
            self.assertIn(self.sha[:12], task_label)
            plan_label = str(self.app._row_nodes[("plan", self.pid)].label)
            self.assertNotIn("b" * 12, plan_label)
            self.assertIn("2c", plan_label)
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            self.app.update_preview()
            await pilot.pause()
            preview = str(self.app.query_one("#preview-body", Static).render())
            self.assertIn("1 commits", preview)
            await settle(pilot)
            self.app.selected = ("plan", self.pid)
            self.app.update_preview()
            await pilot.pause()
            plan_preview = str(self.app.query_one("#preview-body", Static).render())
            self.assertIn("2 commits", plan_preview)

    async def test_rows_show_chips_without_a_marker(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            linked = str(self.app._row_nodes[("task", self.tid)].label)
            repo_only = str(self.app._row_nodes[("task", self.repo_tid)].label)
            bare = str(self.app._row_nodes[("task", self.bare_tid)].label)
            plan = str(self.app._row_nodes[("plan", self.pid)].label)
            for label in (linked, repo_only, bare, plan):
                self.assertNotIn("⎇", label)
            self.assertIn(self.sha[:12], linked)
            self.assertIn("2c", plan)

    async def test_detail_lists_commits(self):
        from textual.widgets import Static

        from lazyplan.tui.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            await pilot.press("enter")
            await pilot.pause()
            await settle(pilot)
            self.assertIsInstance(self.app.screen, DetailScreen)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn(self.sha[:12], body)
            self.assertIn("work", body)

    async def test_task_row_shows_pr_chip_only_when_cached(self):
        Store(self.db).link_forge("task", self.tid, 7, state="merged", checks="pass")
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.refresh_all()
            await pilot.pause()
            label = str(self.app._row_nodes[("task", self.tid)].label)
            self.assertIn("PR", label)
            bare = str(self.app._row_nodes[("task", self.bare_tid)].label)
            self.assertNotIn("PR", bare)

    async def test_source_filters_cycle(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "linked")
            status = str(self.app.query_one("#status").render())
            self.assertIn("source linked", status)
            self.assertIn(("task", self.tid), self.app._row_nodes)
            self.assertNotIn(("task", self.bare_tid), self.app._row_nodes)

            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "pr")
            self.assertNotIn(("task", self.tid), self.app._row_nodes)

            self.app.action_filter_source()
            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "unlinked")
            self.assertIn(("task", self.bare_tid), self.app._row_nodes)
            self.assertNotIn(("task", self.tid), self.app._row_nodes)

            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "claims")
            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "blocked")
            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "attention")
            self.app.action_filter_source()
            await pilot.pause()
            self.assertEqual(self.app.source_filter, "all")
            self.assertIn(("task", self.tid), self.app._row_nodes)
            self.assertIn(("task", self.bare_tid), self.app._row_nodes)

    async def test_g_opens_source_screen(self):
        from lazyplan.tui.screens.source import SourceScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.tid)
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, SourceScreen)

    async def test_detail_hides_empty_commits(self):
        from textual.widgets import Static

        from lazyplan.tui.screens import DetailScreen

        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.bare_tid)
            await pilot.press("enter")
            await pilot.pause()
            await settle(pilot)
            self.assertIsInstance(self.app.screen, DetailScreen)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertNotIn("commits:", body)
            self.assertIn("no linked commits", body)


if __name__ == "__main__":
    unittest.main()
