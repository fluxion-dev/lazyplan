"""The agents panel and sessions hub reap stale rows before they render."""

from __future__ import annotations

import os
import tempfile
import time
import unittest

from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.hub_coordination import SessionsHub
except ImportError:  # pragma: no cover - textual not installed
    create_app = SessionsHub = None  # type: ignore[assignment]


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestReapBeforeRender(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "reap.db"))
        self.plan = self.store.add_plan("Plan")

    def _abandoned(self) -> int:
        session, _ = self.store.start_session(
            "ana",
            plan_id=self.plan.id,
            repo_path=self.store.checkout_path(),
            host="opencode",
            now=time.time() - 3 * 3600,
        )
        return session.id

    async def test_agents_panel_reaps_before_listing(self) -> None:
        session_id = self._abandoned()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            ended = self.store.get_session(session_id)
            assert ended is not None
            self.assertTrue(ended.ended)
            self.assertTrue(ended.auto_closed)

    async def test_sessions_hub_reaps_before_listing(self) -> None:
        session_id = self._abandoned()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            hub = SessionsHub(self.store, self.plan.id)
            app.push_screen(hub)
            await pilot.pause()
            ended = self.store.get_session(session_id)
            assert ended is not None
            self.assertTrue(ended.ended)

    async def test_a_heartbeat_changes_live_state_not_structure(self) -> None:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id)
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            structural = app.store.fingerprint()
            live = app.store.live_fingerprint()
            app.store.touch_session(session.id, phase="awaiting")
            self.assertEqual(app.store.fingerprint(), structural)
            self.assertNotEqual(app.store.live_fingerprint(), live)

    async def test_agents_panel_shows_every_open_session(self) -> None:
        now = time.time()
        for index in range(6):
            self.store.start_session(
                "opencode",
                plan_id=self.plan.id,
                repo_path=self.store.checkout_path(),
                host="opencode",
                host_session=f"session-{index:02d}-{index:04d}",
                now=now,
            )
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            app.update_agents()
            await pilot.pause()
            panel = app.query_one("#agents")
            body = app.query_one("#agents-body")
            text = str(body.render())
            self.assertIn("6 open", panel.border_subtitle)
            for index in range(6):
                self.assertIn(f"{index:04d}", text)

    async def test_empty_state_returns_after_the_row_ends(self) -> None:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id)
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.store.end_session(session.id, "ana", summary="done")
            app.update_agents()
            empty = app.query_one("#agents-empty")
            self.assertTrue(empty.display)


if __name__ == "__main__":
    unittest.main()
