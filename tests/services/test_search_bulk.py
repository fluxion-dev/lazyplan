"""TUI search across context and bulk editing."""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from lazyplan.palette import COMMANDS
from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from lazyplan import tui as tui_mod
except ImportError:  # pragma: no cover
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestSearchBulk(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "search.db")
        store = Store(self.db)
        self.plan = store.add_plan("Plan title", "plan body alpha", goal="plan why", actor="f")
        self.milestone = store.add_milestone(self.plan.id, "Milestone", "delta", actor="f")
        self.t1 = store.add_task(self.milestone.id, "Task one", "epsilon", actor="f").id
        self.t2 = store.add_task(self.milestone.id, "Task two", "plain", actor="f").id
        store.add_note("task", self.t1, "beta note", actor="f")
        store.add_comment("task", self.t1, "gamma comment", actor="f")
        store.add_issue_link(
            "linear", "ENG-9", "ENG-9", "https://x/ENG-9", "issue title", "open", "task", self.t1
        )
        store.claim_task(self.t1, "alice", 300)
        store.set_blocked(self.t2, True, "zeta blocked", actor="f")
        self.store = store
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _ids(self) -> set[int]:
        return {
            task.id
            for _plan, milestones in self.app._filtered_tree()
            for _milestone, tasks in milestones
            for task in tasks
        }

    async def test_search_covers_context(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            for query, expected in [
                ("alpha", {self.t1, self.t2}),
                ("beta", {self.t1}),
                ("gamma", {self.t1}),
                ("ENG-9", {self.t1}),
                ("alice", {self.t1}),
                ("zeta", {self.t2}),
                ("delta", {self.t1, self.t2}),
            ]:
                with self.subTest(query=query):
                    self.app.filter_text = query
                    self.app.refresh_all()
                    await pilot.pause()
                    self.assertEqual(self._ids(), expected)

    async def test_marks_survive_refresh_and_clear(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            await settle(pilot)
            self.app.selected = ("task", self.t1)
            await pilot.press("space")
            await pilot.pause()
            self.assertEqual(self.app.marked, {("task", self.t1)})
            self.assertIn("marked 1", str(self.app.query_one("#status").render()))
            self.app.refresh_all()
            await pilot.pause()
            self.assertEqual(self.app.marked, {("task", self.t1)})
            self.app.action_clear_marks()
            await pilot.pause()
            self.assertEqual(self.app.marked, set())

    async def test_bulk_done_and_undo(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.marked = {("task", self.t1), ("task", self.t2)}
            self.app.action_bulk_done()
            await pilot.pause()
            await pilot.click("#ok")
            await pilot.pause()
            self.assertEqual(self.store.get_task(self.t1).status.value, "done")
            self.assertEqual(self.store.get_task(self.t2).status.value, "done")
            self.app.action_undo_bulk()
            await pilot.pause()
            self.assertEqual(self.store.get_task(self.t1).status.value, "todo")
            self.assertEqual(self.store.get_task(self.t2).status.value, "todo")

    async def test_bulk_block_prompts_and_undoes(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.marked = {("task", self.t1)}
            self.app.action_bulk_block()
            await pilot.pause()
            from textual.widgets import Input

            self.app.screen.query_one("#filter-input", Input).value = "waiting"
            await pilot.click("#ok")
            await pilot.pause()
            await pilot.click("#ok")
            await pilot.pause()
            self.assertTrue(self.store.get_task(self.t1).blocked)
            self.assertEqual(self.store.get_task(self.t1).blocked_reason, "waiting")
            self.app.action_undo_bulk()
            await pilot.pause()
            self.assertFalse(self.store.get_task(self.t1).blocked)

    async def test_bulk_release_reports_conflicts(self):
        self.store.set_blocked(self.t2, False, actor="f")
        self.store.claim_task(self.t2, "other", 300)
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.marked = {("task", self.t1), ("task", self.t2)}
            self.app.action_bulk_release()
            await pilot.pause()
            await pilot.click("#ok")
            await pilot.pause()
            self.assertIsNotNone(self.store.get_claim(self.t1))
            self.assertIsNotNone(self.store.get_claim(self.t2))

    def test_no_bulk_delete_or_archive(self):
        ids = {command.id for command in COMMANDS}
        self.assertNotIn("bulk-delete", ids)
        self.assertNotIn("bulk-archive", ids)

    async def test_large_search_is_bounded(self):
        store = Store(self.db)
        for index in range(1000):
            store.add_task(self.milestone.id, f"Bulk {index}", "plain", actor="f")
        target = store.add_task(self.milestone.id, "Needle task", "find me", actor="f").id
        async with self.app.run_test() as pilot:
            await pilot.pause()
            start = time.monotonic()
            self.app.filter_text = "needle"
            self.app.refresh_all()
            await pilot.pause()
            self.assertEqual(self._ids(), {target})
            self.assertLess(time.monotonic() - start, 30.0)


if __name__ == "__main__":
    unittest.main()
