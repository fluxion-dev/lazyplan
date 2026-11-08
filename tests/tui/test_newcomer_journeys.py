"""Newcomer journeys finish from the screen at both supported sizes."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from textual.widgets import Input

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens.detail import DetailScreen
    from lazyplan.presentation.tui.screens.help import HelpScreen, PaletteScreen
    from lazyplan.presentation.tui.screens.hub_coordination import ClaimsHub, CommentsHub
    from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
    from lazyplan.presentation.tui.screens.hub_provenance import ActivityHub, PullRequestHub
    from lazyplan.presentation.tui.screens.source import SourceScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

SIZES = ((80, 24), (120, 40))


@unittest.skipUnless(
    tui_mod is not None and getattr(tui_mod, "_TEXTUAL_OK", False), "textual not installed"
)
class NewcomerJourneyTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "journey.db")
        store = Store(self.db)
        self.plan = store.add_plan("Journey", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.")
        store.add_criteria("task", self.task.id, "It works")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_inspect_journey_needs_no_cli(self) -> None:
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    await settle(pilot)
                    app.selected = ("task", self.task.id)
                    await pilot.press("enter")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, DetailScreen)
                    await pilot.press("g")
                    await pilot.pause()
                    await app.workers.wait_for_complete()
                    await settle(pilot)
                    self.assertIsInstance(app.screen, SourceScreen)
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, DetailScreen)
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertEqual(len(app.screen_stack), 1)

    async def test_trust_and_provenance_journeys_are_three_steps(self) -> None:
        hubs = (
            ("t", CriteriaHub),
            ("k", ClaimsHub),
            ("m", CommentsHub),
            ("P", PullRequestHub),
            ("A", ActivityHub),
        )
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    await settle(pilot)
                    app.selected = ("task", self.task.id)
                    await pilot.press("enter")
                    await pilot.pause()
                    for key, screen_type in hubs:
                        with self.subTest(key=key):
                            await pilot.press(key)
                            await pilot.pause()
                            self.assertIsInstance(app.screen, screen_type)
                            await pilot.press("escape")
                            await pilot.pause()
                            self.assertIsInstance(app.screen, DetailScreen)

    async def test_capture_organize_and_administer(self) -> None:
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    await settle(pilot)
                    app.override_mode = True
                    await pilot.press("c")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, PaletteScreen)
                    app.screen.query_one("#palette-input", Input).value = "create plan"
                    await pilot.press("enter")
                    await pilot.pause()
                    self.assertTrue(app.screen.query("#dlg"))
                    await pilot.press("escape")
                    await pilot.pause()

                    app.selected = ("plan", self.plan.id)
                    await pilot.press("enter")
                    await pilot.pause()
                    await pilot.press("n")
                    await pilot.pause()
                    self.assertTrue(app.screen.query("#dlg"))
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.press("escape")
                    await pilot.pause()

                    await pilot.press("?")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, HelpScreen)
                    await pilot.press("escape")
                    await pilot.pause()
                    await pilot.press("c")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, PaletteScreen)
                    await pilot.press("escape")
                    await pilot.pause()


if __name__ == "__main__":
    unittest.main()
