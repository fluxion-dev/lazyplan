"""The agents pane shows active sessions and the selected plan's handoff."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from textual.widgets import Static

    from lazyplan.presentation import tui as tui_mod
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class AgentsPanelTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "agents.db")
        store = Store(self.db)
        self.plan = store.add_plan("Session plan", actor="fixture")
        milestone = store.add_milestone(self.plan.id, "M", "As a user.", actor="fixture")
        self.task = store.add_task(
            milestone.id, "Task", "Commit: one.\n\nVerify: test.", actor="fixture"
        )
        services.set_status(store, "task", self.task.id, Status.DOING, actor="fixture")
        self.session, _ = store.start_session(
            "carol", plan_id=self.plan.id, branch="task/x", now=1_000_000
        )

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _body(self, app) -> str:
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.selected = ("task", self.task.id)
            app.update_preview(force=True)
            await pilot.pause()
            return str(app.query_one("#agents-body", Static).render())

    async def test_active_session_names_actor_plan_and_branch(self) -> None:
        body = await self._body(tui_mod.create_app(self.db))
        self.assertIn("@carol", body)
        self.assertIn(f"P{self.plan.id}", body)
        self.assertIn("task/x", body)

    async def test_selected_plan_shows_the_last_handoff(self) -> None:
        store = Store(self.db)
        services.end_session(
            store,
            self.session.id,
            "carol",
            summary="shipped the store",
            handoff="next: T2",
        )
        store.start_session("dave", plan_id=self.plan.id, branch="task/y")
        body = await self._body(tui_mod.create_app(self.db))
        self.assertIn("@dave", body)
        self.assertIn("handoff", body)
        self.assertIn("next: T2", body)

    async def test_empty_state_names_the_next_action(self) -> None:
        empty = Store(os.path.join(self.tmp.name, "empty.db"))
        body = await self._body(tui_mod.create_app(empty.path))
        self.assertIn("no active sessions", body)
        self.assertIn("lpui session start", body)


if __name__ == "__main__":
    unittest.main()
