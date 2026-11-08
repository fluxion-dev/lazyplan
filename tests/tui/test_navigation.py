"""Every screen opens the shared palette and help and leaves consistently."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.infrastructure.upgrade import PIPX, InstallInfo
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
class NavigationHostTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "nav.db")
        store = Store(self.db)
        self.plan = store.add_plan("Navigation", "What", goal="Why")
        milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(milestone.id, "T", "Commit: one.")
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
