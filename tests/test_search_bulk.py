"""TUI search across context and bulk editing."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.store import Store

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
