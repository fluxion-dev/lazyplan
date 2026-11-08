"""Control-room acceptance: launch, panels, detail health, and handoff."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import revisions
from lazyplan.store import Store

try:
    from textual.widgets import Static

    from lazyplan.presentation import tui as tui_mod
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ControlRoomQaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "control-room.db")
        store = Store(self.db)
        self.plan = store.add_plan("Control room", "What we build", goal="Why we build")
        milestone = store.add_milestone(
            self.plan.id, "See the work", "As a human, I want triage.", actor="fixture"
        )
        self.blocked = store.add_task(
            milestone.id, "Blocked task", "Commit: one.\n\nVerify: test.", actor="fixture"
        )
        self.doing = store.add_task(
            milestone.id, "Doing task", "Commit: one.\n\nVerify: test.", actor="fixture"
        )
        store.set_blocked(self.blocked.id, True, "waiting on design", actor="fixture")
        services.set_status(store, "task", self.doing.id, Status.DOING, actor="fixture")
        store.claim_task(self.doing.id, "alice", 300)
        store.add_touchpoint(self.doing.id, "src/app", actor="fixture")
        store.add_question(self.plan.id, "Which host?", actor="fixture")
        store.link_ref(self.plan.id, "https://example.com/epic", title="Epic", actor="fixture")
        revisions.approve(store, self.plan.id, actor="fixture")
        store.update_plan(self.plan.id, description="changed", actor="fixture")
        first, _ = store.start_session("bob", plan_id=self.plan.id, branch="task/a")
        store.end_session(first.id, "bob", summary="shipped", handoff="next: T2")
        store.start_session("carol", plan_id=self.plan.id, branch="task/x")
        self.store = store

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_clearing_a_done_task_releases_its_claim(self) -> None:
        app = tui_mod.create_app(self.db)
        app.override_mode = True
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.selected = ("task", self.doing.id)
            await pilot.press("s")
            await pilot.pause()
            self.assertEqual(self.store.get_task(self.doing.id).status, Status.DONE)
            self.assertIsNone(self.store.get_claim(self.doing.id))

    async def test_control_room_launch_panels_and_detail(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.assertEqual(app.plan_mode.value, "active")
            self.assertIn("active", str(app.query_one("#nav").border_title))
            self.assertIn(("plan", self.plan.id), app._row_nodes)
            self.assertIn(("task", self.blocked.id), app._row_nodes)

            app.selected = ("plan", self.plan.id)
            app.update_preview(force=True)
            await pilot.pause()
            strip = str(app.query_one("#preview-strip", Static).render())
            self.assertIn("health", strip)
            self.assertIn("open question", strip)
            self.assertIn("blocked task", strip)
            agents = str(app.query_one("#agents-body", Static).render())
            self.assertIn("@carol", agents)
            self.assertIn("handoff", agents)
            self.assertIn("next: T2", agents)

            await pilot.press("enter")
            await pilot.pause()
            body = str(app.screen.query_one("#detail-body", Static).render())
            self.assertIn("approval r1", body)
            self.assertIn("changes since approval", body)
            self.assertIn("Which host?", body)
            self.assertIn("Epic", body)
            self.assertIn("claims 1", body)
            self.assertIn("handoff", body)
            self.assertIn("next: T2", body)

            await pilot.press("escape")
            app.selected = ("task", self.doing.id)
            await pilot.press("enter")
            await pilot.pause()
            task_body = str(app.screen.query_one("#detail-body", Static).render())
            self.assertIn("@alice", task_body)
            self.assertIn("src/app", task_body)
            self.assertIn("handoff", task_body)


if __name__ == "__main__":
    unittest.main()
