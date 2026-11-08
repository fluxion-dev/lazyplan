"""Every screen opens the shared palette and help and leaves consistently."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.infrastructure.upgrade import PIPX, InstallInfo
from lazyplan.presentation.tui.navigation import NavEntry, NavigationHistory
from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import (
        DetailScreen,
        ExportScreen,
        HelpScreen,
        NewPlanScreen,
        PaletteScreen,
        UpdateScreen,
    )
    from lazyplan.presentation.tui.screens.source import SourceScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class NavigationHistoryTest(unittest.TestCase):
    def test_push_back_forward_restores_order(self) -> None:
        history = NavigationHistory()
        self.assertEqual(history.breadcrumb(), "plans")
        history.push(NavEntry("detail", "task", 7, "P1 › M2 › T7"))
        self.assertEqual(history.current.selection, ("task", 7))
        self.assertEqual(history.breadcrumb(), "plans › P1 › M2 › T7")
        entry = history.back()
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.screen, "tree")
        forward = history.forward()
        self.assertIsNotNone(forward)
        assert forward is not None
        self.assertEqual(forward.screen, "detail")
        self.assertEqual(forward.selection, ("task", 7))

    def test_new_push_drops_the_forward_branch(self) -> None:
        history = NavigationHistory()
        history.push(NavEntry("detail", "plan", 1, "P1"))
        history.push(NavEntry("source", "plan", 1, "P1 source"))
        history.back()
        history.push(NavEntry("detail", "task", 9, "P1 › M1 › T9"))
        self.assertEqual(history.current.selection, ("task", 9))
        self.assertIsNone(history.forward())
        self.assertEqual(history.breadcrumb(), "plans › P1 › P1 › M1 › T9")


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class NavigationHostTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "nav.db")
        store = Store(self.db)
        self.plan = store.add_plan("Navigation", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.")
        self.store = store

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _leave_text_focus(self, pilot) -> None:
        """Blur an input so screen bindings can receive printable keys."""
        from textual.widgets import Input, TextArea

        if isinstance(self.app.focused, (Input, TextArea)):
            self.app.set_focus(None)
            await pilot.pause()

    async def _assert_overlays(self, pilot) -> None:
        await pilot.press("c")
        await pilot.pause()
        self.assertIsInstance(self.app.screen, PaletteScreen)
        await pilot.press("escape")
        await pilot.pause()
        await self._leave_text_focus(pilot)
        await pilot.press("?")
        await pilot.pause()
        self.assertIsInstance(self.app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()

    async def test_palette_and_help_open_on_the_main_tree(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            await self._assert_overlays(pilot)

    async def test_palette_and_help_open_on_detail(self) -> None:
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            await self._assert_overlays(pilot)
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_palette_and_help_open_on_source(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause()
            await self._assert_overlays(pilot)
            self.assertIsInstance(self.app.screen, SourceScreen)

    async def test_palette_and_help_open_on_export(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(ExportScreen(self.store, self.plan.id, "Navigation"))
            await pilot.pause()
            await self._leave_text_focus(pilot)
            await self._assert_overlays(pilot)
            self.assertIsInstance(self.app.screen, ExportScreen)

    async def test_palette_and_help_open_on_update_and_forms(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(
                UpdateScreen("0.1.0", "0.2.0", InstallInfo(PIPX, True), windows=False)
            )
            await pilot.pause()
            await self._assert_overlays(pilot)
            await pilot.press("escape")
            await pilot.pause()
            self.app.push_screen(NewPlanScreen())
            await pilot.pause()
            await self._leave_text_focus(pilot)
            await self._assert_overlays(pilot)

    async def test_escape_returns_to_the_previous_screen(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(self.app.screen, DetailScreen)

    async def test_back_restores_the_exact_prior_selection(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(self.app.selected, ("task", self.task.id))

    async def test_forward_replays_the_detail_screen(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(self.app.screen, DetailScreen)
            await pilot.press("]")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(self.app.selected, ("plan", self.plan.id))

    async def test_breadcrumb_names_every_level(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            screen = self.app.screen
            assert isinstance(screen, DetailScreen)
            self.assertEqual(
                screen._breadcrumb(),
                f"plans › P{self.plan.id} › M{self.milestone.id} › T{self.task.id}",
            )
            self.assertEqual(
                self.app.breadcrumb(),
                f"plans › P{self.plan.id} › M{self.milestone.id} › T{self.task.id}",
            )

    async def test_source_back_returns_to_detail_then_tree(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, SourceScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(self.app.selected, ("task", self.task.id))
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(self.app.selected, ("task", self.task.id))

    async def test_q_quits_from_detail(self) -> None:
        self.app = tui_mod.create_app(self.db)
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("plan", self.plan.id)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            self.assertTrue(self.app._exit)
