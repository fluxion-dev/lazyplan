"""Every screen stays usable at 80x24 and 120x40."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pilot_settle import settle  # noqa: E402

from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.screens import (
        ConfirmScreen,
        HelpScreen,
        NewMilestoneScreen,
        NewPlanScreen,
        NewTaskScreen,
        PaletteScreen,
    )
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
                    await pilot.press("e")
                    await pilot.pause()
                    edit = app.screen.query_one("#detail-edit")
                    self.assertTrue(_within(edit.region, width, height))
                    await pilot.press("ctrl+s")
                    await pilot.pause()
                    await pilot.press("escape")
                    await pilot.pause()

    async def test_forms_palette_help_and_confirm_at_both_sizes(self):
        for width, height in SIZES:
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    app.push_screen(NewPlanScreen())
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
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
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(HelpScreen())
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#help").region, width, height))
                    await pilot.press("escape")
                    await pilot.pause()

                    app.push_screen(ConfirmScreen("Delete plan?", confirm_label="Delete"))
                    await pilot.pause()
                    self.assertTrue(_within(app.screen.query_one("#dlg").region, width, height))
                    await pilot.press("escape")
                    await pilot.pause()


if __name__ == "__main__":
    unittest.main()
