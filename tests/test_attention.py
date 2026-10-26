"""TUI Attention filter: categories, composition, and status count."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
except ImportError:  # pragma: no cover
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestAttention(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "attention.db")
        self.store = Store(self.db)
        plan = self.store.add_plan("P", actor="fixture")
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        self.tasks = {}
        for name in ("blocked", "expired", "aging", "gap", "red", "fresh", "plain"):
            self.tasks[name] = self.store.add_task(milestone.id, name, "desc", actor="fixture").id
        self.store.set_blocked(self.tasks["blocked"], True, "waiting", actor="fixture")
        self.store.claim_task(self.tasks["expired"], "alice", 1, now=1)
        with mock.patch("lazyplan.store.time.time", return_value=1):
            services.set_status(
                self.store, "task", self.tasks["aging"], Status.DOING, actor="fixture"
            )
        self.store.add_criteria("task", self.tasks["gap"], "open", actor="fixture")
        services.set_status(self.store, "task", self.tasks["gap"], Status.DONE, actor="fixture")
        self.store.link_forge(
            "task",
            self.tasks["red"],
            7,
            checks="fail",
            state="open",
            title="red",
            actor="fixture",
        )
        services.set_status(self.store, "task", self.tasks["fresh"], Status.DOING, actor="fixture")
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _visible_ids(self) -> set[int]:
        return {
            task.id
            for _plan, milestones in self.app._filtered_tree()
            for _milestone, tasks in milestones
            for task in tasks
        }

    async def test_attention_categories_and_status_count(self):
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            self.app.source_filter = "attention"
            self.app.refresh_all("attention")
            await pilot.pause()
            visible = self._visible_ids()
            for name in ("blocked", "expired", "aging", "gap", "red"):
                self.assertIn(self.tasks[name], visible, name)
            for name in ("fresh", "plain"):
                self.assertNotIn(self.tasks[name], visible, name)
            status = str(self.app.query_one("#status").render())
            self.assertIn("attention 5", status)

    async def test_attention_composes_with_status_filter(self):
        async with self.app.run_test() as pilot:
            await pilot.pause()
            self.app.source_filter = "attention"
            self.app.status_filter = Status.DONE
            self.app.refresh_all()
            await pilot.pause()
            visible = self._visible_ids()
            self.assertEqual(visible, {self.tasks["gap"]})


if __name__ == "__main__":
    unittest.main()
