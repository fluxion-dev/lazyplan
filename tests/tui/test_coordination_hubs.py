"""Coordination hubs: claims, touch-points, sessions, comments, and notes."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from textual.widgets import Input, OptionList

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens.forms import FilterPromptScreen
    from lazyplan.presentation.tui.screens.hub_coordination import (
        ClaimsHub,
        CommentsHub,
        SessionsHub,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class CoordinationHubTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "coord.db")
        store = Store(self.db)
        self.plan = store.add_plan("Coordination", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.")
        self.other = store.add_task(self.milestone.id, "Other", "Commit: one.")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _app(self):
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True
        return self.app

    async def test_claims_hub_renews_releases_and_shows_overlap(self) -> None:
        self.store.claim_task(self.task.id, "tui", ttl_seconds=60)
        self.store.claim_task(self.other.id, "alice", ttl_seconds=60)
        self.store.add_touchpoint(self.task.id, "src/app.py", actor="alice")
        self.store.add_touchpoint(self.other.id, "src/app.py", actor="alice")
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(ClaimsHub(self.store, task_id=self.task.id, plan_id=self.plan.id))
            await pilot.pause()
            options = app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 2)
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("@tui", preview)
            self.assertIn("overlap", preview)
            before = next(
                row
                for row in self.store.list_claims(include_expired=True, plan_id=self.plan.id)
                if int(row["task_id"]) == self.task.id
            )
            await pilot.press("x")
            await pilot.pause()
            after = next(
                row
                for row in self.store.list_claims(include_expired=True, plan_id=self.plan.id)
                if int(row["task_id"]) == self.task.id
            )
            self.assertGreaterEqual(float(after["expires_at"]), float(before["expires_at"]))
            hub = app.screen
            options.highlighted = next(
                index
                for index, entry in enumerate(hub.entries)
                if entry.oid == self.task.id and entry.kind == "claim"
            )
            await pilot.pause()
            await pilot.press("d")
            await pilot.pause()
            self.assertEqual(
                len(self.store.list_claims(include_expired=True, plan_id=self.plan.id)), 1
            )

    async def test_claims_hub_force_release_and_touchpoints(self) -> None:
        self.store.claim_task(self.task.id, "alice", ttl_seconds=60)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(ClaimsHub(self.store, task_id=self.task.id, plan_id=self.plan.id))
            await pilot.pause()
            await pilot.press("D")
            await pilot.pause()
            self.assertEqual(self.store.list_claims(include_expired=True, plan_id=self.plan.id), [])
            await pilot.press("l")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterPromptScreen)
            app.screen.query_one("#filter-input", Input).value = "src/app.py"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(self.store.list_touchpoints(self.task.id), ["src/app.py"])

    async def test_sessions_hub_starts_ends_and_shows_handoff(self) -> None:
        first = self.store.start_session("tui", plan_id=self.plan.id, branch="feat/a")[0]
        self.store.end_session(first.id, "alice", summary="done", handoff="next: T2")
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(SessionsHub(self.store, self.plan.id))
            await pilot.pause()
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("next: T2", preview)
            await pilot.press("a")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = "feat/b"
            await pilot.press("enter")
            await pilot.pause()
            sessions = self.store.list_sessions(plan_id=self.plan.id, limit=10)
            self.assertEqual(len(sessions), 2)
            self.assertFalse(sessions[0].ended)
            await pilot.press("x")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterPromptScreen)
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(self.store.list_sessions(plan_id=self.plan.id, limit=10)[0].ended)

    async def test_comments_hub_adds_notes_resolves_and_filters(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(CommentsHub(self.store, "task", self.task.id))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = "needs work"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("n")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = "handoff"
            await pilot.press("enter")
            await pilot.pause()
            options = app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 2)
            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(self.store.list_comments("task", self.task.id)[0].resolved)
            await pilot.press("x")
            await pilot.pause()
            self.assertFalse(self.store.list_comments("task", self.task.id)[0].resolved)
            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(self.store.list_comments("task", self.task.id)[0].resolved)
            await pilot.press("u")
            await pilot.pause()
            self.assertEqual(app.screen.query_one("#hub-list", OptionList).option_count, 1)

    async def test_detail_and_agents_open_coordination_hubs(self) -> None:
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            self.assertIsInstance(app.screen, ClaimsHub)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            self.assertIsInstance(app.screen, SessionsHub)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("m")
            await pilot.pause()
            self.assertIsInstance(app.screen, CommentsHub)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            app.selected = ("plan", self.plan.id)
            app.query_one("#agents").on_click()
            await pilot.pause()
            self.assertIsInstance(app.screen, SessionsHub)

    async def test_claims_hub_shows_expired_and_refuses_foreign_release(self) -> None:
        self.store.claim_task(self.task.id, "alice", ttl_seconds=1, now=100.0)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(ClaimsHub(self.store, task_id=self.task.id, plan_id=self.plan.id))
            await pilot.pause()
            preview = str(app.screen.query_one("#hub-preview-body").render())
            self.assertIn("expired", preview)
            await pilot.press("d")
            await pilot.pause()
            self.assertIsNotNone(self.store.get_claim(self.task.id))

    async def test_session_error_is_visible_and_leaves_state_alone(self) -> None:
        self.store.start_session("tui", plan_id=self.plan.id, branch="feat/a")
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            app.push_screen(SessionsHub(self.store, self.plan.id))
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            app.screen.query_one("#filter-input", Input).value = "feat/b"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(len(self.store.list_sessions(plan_id=self.plan.id, limit=10)), 1)

    async def test_coordination_hubs_reuse_the_framework(self) -> None:
        from tests.support.paths import ROOT

        source = (
            ROOT / "src/lazyplan/presentation/tui/screens/hub_coordination.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("OptionList", source)
        self.assertNotIn("class HubScreen", source)

    async def test_empty_states_and_viewports(self) -> None:
        for size in ((80, 24), (120, 40)):
            with self.subTest(size=size):
                app = self._app()
                async with app.run_test(size=size) as pilot:
                    await settle(pilot)
                    app.push_screen(
                        ClaimsHub(self.store, task_id=self.task.id, plan_id=self.plan.id)
                    )
                    await pilot.pause()
                    preview = str(app.screen.query_one("#hub-preview-body").render())
                    self.assertIn("No claims", preview)
                    page = app.screen.query_one("#hub-page")
                    self.assertLessEqual(page.region.x + page.region.width, size[0])
                    self.assertLessEqual(page.region.y + page.region.height, size[1])
