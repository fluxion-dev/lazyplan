"""Every screen stays usable at 80x24 and 120x40."""

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store
from lazyplan.upgrade import PIPX, InstallInfo
from tests.support.pilot import settle

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.screens import (
        ConfirmScreen,
        DetailScreen,
        HelpScreen,
        NewMilestoneScreen,
        NewPlanScreen,
        NewTaskScreen,
        PaletteScreen,
        UpdateScreen,
    )
    from lazyplan.tui.screens.source import SourceScreen
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]

SIZES = ((80, 24), (120, 40))


def _within(region, width: int, height: int) -> bool:
    return (
        region.x >= 0
        and region.y >= 0
        and region.x + region.width <= width
        and region.y + region.height <= height
    )


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestViewports(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("Plan title", "What we build", goal="Why we build").id
        self.sid = store.add_milestone(self.pid, "Milestone title", "Details").id
        self.tid = store.add_task(self.sid, "Task title", "Details").id
        store.add_criteria("plan", self.pid, "Criterion one")
        self.store = Store(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_shell_and_detail_at_both_sizes(self):
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    await pilot.pause()
                    self.assertTrue(_within(app.query_one("#panel").region, width, height))
                    await settle(pilot)
                    app.selected = ("plan", self.pid)
                    await pilot.press("enter")
                    await pilot.pause()
                    page = app.screen.query_one("#detail-page")
                    self.assertTrue(_within(page.region, width, height))
                    self.assertEqual(page.border_title, "DETAIL")
                    await pilot.press("e")
                    await pilot.pause()
                    edit = app.screen.query_one("#detail-edit")
                    self.assertTrue(_within(edit.region, width, height))
                    await pilot.press("ctrl+s")
                    await pilot.pause()
                    await pilot.press("escape")
                    await pilot.pause()

    async def test_layout_tiers_and_breakpoints(self):
        for width in (70, 80, 100, 120, 160):
            with self.subTest(width=width):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, 30)) as pilot:
                    await pilot.pause()
                    main = app.query_one("#main")
                    preview = app.query_one("#preview")
                    metrics = app.query_one("#metrics")
                    if width < 100:
                        self.assertTrue(main.has_class("narrow"))
                        self.assertFalse(preview.display)
                        self.assertFalse(metrics.display)
                    else:
                        self.assertFalse(main.has_class("narrow"))
                        self.assertTrue(preview.display)
                        self.assertTrue(metrics.display)
                    self.assertEqual(main.has_class("compact"), width < 80)
                    self.assertEqual(main.has_class("wide"), width >= 120)
                    if width >= 120:
                        self.assertGreater(
                            app.query_one("#nav").region.width,
                            preview.region.width,
                        )

    async def test_main_shell_regions_at_four_sizes(self):
        for width, height in ((80, 24), (100, 30), (120, 40), (160, 50)):
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    await pilot.pause()
                    for selector in ("#panel", "#main", "#nav", "#status", "#hints"):
                        self.assertTrue(
                            _within(app.query_one(selector).region, width, height),
                            selector,
                        )
                    preview = app.query_one("#preview")
                    metrics = app.query_one("#metrics")
                    if width >= 100:
                        self.assertTrue(_within(preview.region, width, height))
                        self.assertEqual(preview.border_title, "PREVIEW")
                        self.assertTrue(_within(metrics.region, width, height))
                        self.assertEqual(metrics.region.height, 13)
                    else:
                        self.assertFalse(preview.display)
                        self.assertFalse(metrics.display)

    async def test_screens_fit_in_both_themes(self):
        screens = (
            (DetailScreen(self.store, "plan", self.pid), "#detail-page"),
            (SourceScreen(self.store, "plan", self.pid), "#source-page"),
            (PaletteScreen({"create-plan": None}), "#dlg"),
            (HelpScreen(), "#help"),
            (ConfirmScreen("Delete plan?"), "#dlg"),
            (UpdateScreen("0.1.0", "0.2.0", InstallInfo(PIPX, True)), "#dlg"),
        )
        for theme in ("dark", "light"):
            for width, height in SIZES:
                with self.subTest(theme=theme, size=(width, height)):
                    with mock.patch.dict(os.environ, {"LAZYPLAN_THEME": theme}):
                        app = tui_mod.create_app(self.db)
                    async with app.run_test(size=(width, height)) as pilot:
                        await pilot.pause()
                        self.assertEqual(app.current_theme.dark, theme == "dark")
                        for screen, selector in screens:
                            app.push_screen(screen)
                            await pilot.pause(0.4)
                            self.assertTrue(
                                _within(app.screen.query_one(selector).region, width, height),
                                selector,
                            )
                            app.pop_screen()
                            await pilot.pause()

    async def test_forms_palette_help_and_confirm_at_both_sizes(self):
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    app.push_screen(NewPlanScreen())
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    self.assertEqual(app.screen.query_one("#dlg").border_title, "CREATE")
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(NewMilestoneScreen(self.pid, context=f"P{self.pid}"))
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(NewTaskScreen(self.sid, context=f"M{self.sid}"))
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(PaletteScreen(app._palette_context()))
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    self.assertEqual(app.screen.query_one("#dlg").border_title, "COMMANDS")
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(HelpScreen())
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#help").region, width, height))
                    self.assertEqual(app.screen.query_one("#help").border_title, "HELP")
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(ConfirmScreen("Delete plan?", confirm_label="Delete"))
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    self.assertEqual(app.screen.query_one("#dlg").border_title, "CONFIRM")
                    await pilot.press("escape")
                    await pilot.pause()


if __name__ == "__main__":
    unittest.main()
