"""The agents panel lists live claims and follows them without a keypress."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
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
        self.plan = self.store.add_plan("Agents plan", worktree_required=False)
        milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(milestone.id, "Wire the panel")
        self.other = self.store.add_task(milestone.id, "Write the docs")

    def body(self, app) -> str:
        return str(app.query_one("#agents-body").render())

    async def settle(self, pilot) -> None:
        await pilot.pause(0.6)

    async def test_no_claims_hides_the_panel(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await self.settle(pilot)
            self.assertFalse(app.query_one("#agents").display)

    async def test_each_claim_is_one_row_naming_actor_task_and_plan(self) -> None:
        services.start_claim(self.store, self.task.id, "claude")
        services.start_claim(self.store, self.other.id, "codex")
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await self.settle(pilot)
            panel = app.query_one("#agents")
            self.assertTrue(panel.display)
            text = self.body(app)
            self.assertIn(f"@claude T{self.task.id} Wire the panel", text)
            self.assertIn(f"@codex T{self.other.id} Write the docs", text)
            self.assertIn(f"P{self.plan.id} Agents plan", text)
            self.assertEqual(panel.border_subtitle, "2 tasks · 2 agents")

    async def test_another_process_moving_to_doing_shows_without_a_keypress(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await self.settle(pilot)
            other = Store(self.store.path)
            services.set_status(other, "task", self.task.id, Status.DOING, actor="claude")
            await self.settle(pilot)
            self.assertIn(f"@claude T{self.task.id}", self.body(app))
            services.set_status(other, "task", self.task.id, Status.DONE, actor="claude")
            await self.settle(pilot)
            self.assertFalse(app.query_one("#agents").display)

    async def test_a_release_clears_the_row(self) -> None:
        services.start_claim(self.store, self.task.id, "claude")
        app = create_app(self.store.path)
        async with app.run_test(size=(160, 40)) as pilot:
            await self.settle(pilot)
            self.assertIn("@claude", self.body(app))
            services.release_task_claim(Store(self.store.path), self.task.id, "claude")
            await self.settle(pilot)
            self.assertFalse(app.query_one("#agents").display)

    async def test_clicking_the_agents_pane_does_not_open_the_hub(self) -> None:
        services.start_claim(self.store, self.task.id, "claude")
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.settle(pilot)
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
