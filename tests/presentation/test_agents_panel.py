"""The agents panel renders the exact registry and never infers time."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.hub_coordination import AgentsHub
except ImportError:  # pragma: no cover - textual not installed
    create_app = AgentsHub = None  # type: ignore[assignment]


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestAgentsPanel(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "panel.db"))
        self.plan = self.store.add_plan("Plan")

    def _agent(self, **fields: object):
        values: dict[str, object] = {
            "host": "opencode",
            "agent": "builder",
            "plan_id": self.plan.id,
            "worktree": self.store.checkout_path(),
        }
        values.update(fields)
        return self.store.add_agent("ana", **values)

    async def test_agents_panel_shows_every_open_agent(self) -> None:
        for index in range(6):
            self._agent(host_session=f"session-{index:02d}-{index:04d}")
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            app.update_agents()
            await pilot.pause()
            panel = app.query_one("#agents")
            text = str(app.query_one("#agents-body").render())
            self.assertIn("6 open", panel.border_subtitle)
            self.assertIn("A1", text)
            self.assertIn("A6", text)

    async def test_agents_panel_shows_plan_task_branch_and_status(self) -> None:
        self._agent(branch="task/94-panel", task_id=None)
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            app.update_agents()
            await pilot.pause()
            text = str(app.query_one("#agents-body").render())
            self.assertIn(f"P{self.plan.id} Plan", text)
            self.assertIn("task/94-panel", text)
            self.assertIn("starting", text)

    async def test_lost_and_unbound_rows_paint_distinctly(self) -> None:
        lost = self._agent(host_session="lost-one", pid=999_999)
        self.store.transition_agent(lost.id, "lost", event="lost")
        unbound = self.store.add_agent(
            "ana", host="claude", agent="wanderer", unbound_reason="no registered plan worktree"
        )
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            app.update_agents()
            await pilot.pause()
            panel = app.query_one("#agents")
            text = str(app.query_one("#agents-body").render())
            self.assertIn("lost", text)
            self.assertIn("unbound", text)
            self.assertIn("1 lost", panel.border_subtitle)
            self.assertIn("1 unbound", panel.border_subtitle)
            self.assertIn(f"A{unbound.id}", text)

    async def test_sweep_marks_a_dead_pid_lost_before_rendering(self) -> None:
        agent = self._agent(pid=424242, process_start="1")
        app = create_app(self.store.path)
        with (
            mock.patch("lazyplan.services.agents.process_alive", return_value=False),
            mock.patch("lazyplan.infrastructure.process.process_start", return_value="1"),
        ):
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.update_agents()
                await pilot.pause()
        self.assertEqual(self.store.get_agent(agent.id).status, "lost")

    async def test_advance_repaints_cached_rows_without_a_store_read(self) -> None:
        self._agent(branch="task/19-pane")
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one("#agents")
            body = app.query_one("#agents-body")
            before = str(body.render())
            with mock.patch.object(
                app.store, "list_agents", side_effect=AssertionError("store read")
            ):
                changed = panel.advance(1)
            self.assertTrue(changed)
            self.assertEqual(str(body.render()).count("\n"), before.count("\n"))

    async def test_clicking_the_agents_pane_does_not_open_the_hub(self) -> None:
        self._agent()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one("#agents")
            stack = len(app.screen_stack)
            await pilot.click("#agents")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), stack)
            self.assertNotIsInstance(app.screen, AgentsHub)
            self.assertIsNot(app.focused, panel)

    async def test_palette_handler_opens_the_agents_hub(self) -> None:
        from lazyplan.presentation.tui.palette_handlers import palette_handlers

        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.selected = ("plan", self.plan.id)
            palette_handlers(app)["open_agents_hub"]()
            await pilot.pause()
            self.assertIsInstance(app.screen, AgentsHub)

    async def test_a_transition_changes_live_state_not_structure(self) -> None:
        agent = self._agent()
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            structural = app.store.fingerprint()
            live = app.store.live_fingerprint()
            app.store.transition_agent(agent.id, "waiting", event="stop")
            self.assertEqual(app.store.fingerprint(), structural)
            self.assertNotEqual(app.store.live_fingerprint(), live)

    async def test_the_poll_interval_is_quarter_second(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            intervals = [
                timer._interval for timer in app._timers if getattr(timer, "_interval", 0) == 0.25
            ]
            self.assertTrue(intervals)


if __name__ == "__main__":
    unittest.main()
