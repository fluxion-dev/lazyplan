"""Palette: context rules, match count, viewport fit, and scrolling."""

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import help as help_mod
from lazyplan import palette
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.screens import PaletteScreen
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestPalette(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("P").id
        self.sid = store.add_milestone(self.pid, "S").id
        self.tid = store.add_task(self.sid, "T").id
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def test_context_disables_impossible_commands(self):
        self.app.selected = ("plan", self.pid)
        context = self.app._palette_context()
        self.assertIsNone(context["create-milestone"])
        self.assertEqual(context["create-task"], "Select a milestone first")
        self.app.selected = None
        self.assertEqual(self.app._palette_context()["edit-selection"], "Select a row first")

    def test_context_enables_task_creation_from_a_milestone(self):
        self.app.selected = ("milestone", self.sid)
        context = self.app._palette_context()
        self.assertIsNone(context["create-task"])
        self.assertIsNone(context["create-milestone"])

    def test_git_commands_are_palette_only_and_context_gated(self):

        for command_id in ("git-status", "git-refresh", "git-capture"):
            command = palette.by_id(command_id)
            assert command is not None
            self.assertTrue(command.tui_only)
            self.assertTrue(command.handler)
        self.app.selected = None
        context = self.app._palette_context()
        self.assertEqual(context["git-status"], "Select a row first")
        self.assertEqual(context["git-capture"], "Select a row first")
        self.app.selected = ("task", self.tid)
        context = self.app._palette_context()
        self.assertIsNone(context["git-status"])
        self.assertIsNone(context["git-refresh"])
        self.assertIsNone(context["git-capture"])
        self.assertIsNone(context["open-pr"])

    def test_open_pr_uses_the_first_linked_url(self):
        url = "https://github.com/org/repo/pull/7"
        self.store.link_forge("task", self.tid, 7, url=url, title="Fix login")
        self.app.selected = ("task", self.tid)
        with mock.patch("lazyplan.tui.actions.webbrowser.open") as opener:
            self.app.action_open_pr()
        opener.assert_called_once_with(url)

    def test_open_pr_without_a_link_notifies(self):
        self.app.selected = ("task", self.tid)
        with mock.patch("lazyplan.tui.actions.webbrowser.open") as opener:
            self.app.action_open_pr()
        opener.assert_not_called()

    async def test_matching_and_count(self):
        from textual.widgets import Input, Label

        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(PaletteScreen(self.app._palette_context()))
            await pilot.pause()
            title = self.app.screen.query_one("#palette-title", Label)
            self.assertIn("type to search", str(title.content))
            search = self.app.screen.query_one("#palette-input", Input)
            search.value = "task"
            await pilot.pause()
            self.assertIn("command", str(title.content))
            search.value = "zzz-nope"
            await pilot.pause()
            self.assertIn("0 commands", str(title.content))

    async def test_palette_fits_and_scrolls_at_80x24(self):
        from textual.widgets import OptionList

        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(PaletteScreen(self.app._palette_context()))
            await pilot.pause()
            dialog = self.app.screen.query_one("#dlg")
            region = dialog.region
            self.assertLessEqual(region.x + region.width, 80)
            self.assertLessEqual(region.y + region.height, 24)
            options = self.app.screen.query_one("#palette-list", OptionList)
            self.assertGreater(options.virtual_size.height, options.size.height)

    def test_help_text_is_task_grouped(self):

        for group in ("MOVE", "CHANGE", "FIND", "APP"):
            self.assertIn(group, help_mod.HELP_TEXT)
        self.assertIn("lpui help", help_mod.HELP_TEXT)

    async def test_help_fits_and_scrolls_at_80x24(self):
        from textual.containers import VerticalScroll

        from lazyplan.tui.screens import HelpScreen

        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(HelpScreen())
            await pilot.pause()
            page = self.app.screen.query_one("#help")
            region = page.region
            self.assertLessEqual(region.x + region.width, 80)
            self.assertLessEqual(region.y + region.height, 24)
            scroller = self.app.screen.query_one("#help-scroll", VerticalScroll)
            self.assertGreater(scroller.virtual_size.height, scroller.size.height)


if __name__ == "__main__":
    unittest.main()
