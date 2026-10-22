"""Create/edit forms: labeled fields, explicit targets, and a dirty guard."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.store import Store

try:
    from lazyplan.screens import (
        ConfirmScreen,
        NewMilestoneScreen,
        NewPlanScreen,
        NewTaskScreen,
    )
except ImportError:  # stdlib-only interpreter: no textual, no screens
    ConfirmScreen = None  # type: ignore[assignment]


@unittest.skipUnless(ConfirmScreen is not None, "textual not installed")
class TestForms(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("P").id
        self.sid = store.add_milestone(self.pid, "S").id

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def _app(self):
        from lazyplan.tui import create_app

        return create_app(self.db)

    async def test_plan_form_has_labels_and_fits_80x24(self):
        from textual.widgets import Label

        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(NewPlanScreen())
            await pilot.pause()
            labels = {str(label.content) for label in app.screen.query(Label)}
            self.assertTrue({"New plan", "Title", "Why", "What"} <= labels)
            dialog = app.screen.query_one("#dlg")
            region = dialog.region
            self.assertLessEqual(region.x + region.width, 80)
            self.assertLessEqual(region.y + region.height, 24)

    async def test_task_form_names_its_parent(self):
        from textual.widgets import Label

        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(NewTaskScreen(self.sid, context="P2 › M3"))
            await pilot.pause()
            labels = {str(label.content) for label in app.screen.query(Label)}
            self.assertIn("New task in P2 › M3", labels)

    async def test_milestone_form_names_its_plan(self):
        from textual.widgets import Label

        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(NewMilestoneScreen(self.pid, context="P7"))
            await pilot.pause()
            labels = {str(label.content) for label in app.screen.query(Label)}
            self.assertIn("New milestone in P7", labels)

    async def test_dirty_escape_prompts_and_cancel_keeps_form(self):
        from textual.widgets import Input

        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(NewPlanScreen())
            await pilot.pause()
            app.screen.query_one("#f-title", Input).value = "Draft"
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(app.screen, NewPlanScreen)
            self.assertEqual(app.screen.query_one("#f-title", Input).value, "Draft")

    async def test_clean_escape_closes_without_prompt(self):
        app = self._app()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(NewPlanScreen())
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)


if __name__ == "__main__":
    unittest.main()
