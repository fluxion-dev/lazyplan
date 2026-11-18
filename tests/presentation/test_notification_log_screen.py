"""The notification log overlay scrolls, clears, copies, closes, and fits narrow."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from textual.widgets import OptionList

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.notification_log import NotificationLogScreen
    from lazyplan.presentation.tui.widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError as exc:  # pragma: no cover - textual not installed
    raise unittest.SkipTest(f"textual not installed: {exc}") from None

NO_UPDATE = mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"})


class NotificationLogScreenTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def open_log(self, app, pilot) -> NotificationLogScreen:
        app.action_notification_log()
        await pilot.pause()
        self.assertIsInstance(app.screen, NotificationLogScreen)
        return app.screen

    @staticmethod
    def options(screen: NotificationLogScreen) -> list[str]:
        listing = screen.query_one("#log-list", OptionList)
        return [
            str(listing.get_option_at_index(index).prompt) for index in range(listing.option_count)
        ]

    async def test_the_overlay_lists_entries_newest_last(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("first")
                app.notify("second")
                screen = await self.open_log(app, pilot)
                texts = self.options(screen)
                self.assertEqual(len(texts), 2)
                self.assertIn("first", texts[0])
                self.assertIn("second", texts[1])
                listing = screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.highlighted, 1)

    async def test_the_empty_log_says_so(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notification_log.clear()
                screen = await self.open_log(app, pilot)
                listing = screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.option_count, 1)
                self.assertTrue(listing.get_option_at_index(0).disabled)
                self.assertIn("Nothing logged yet", str(listing.get_option_at_index(0).prompt))

    async def test_x_clears_every_entry(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("broke", severity="error")
                screen = await self.open_log(app, pilot)
                self.assertEqual(len(app.notification_log), 1)
                await pilot.press("x")
                await pilot.pause()
                self.assertEqual(len(app.notification_log), 0)
                listing = screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.option_count, 1)
                self.assertTrue(listing.get_option_at_index(0).disabled)

    async def test_y_copies_the_selected_entry(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("first")
                app.notify("second")
                await self.open_log(app, pilot)
                selected = app.notification_log.snapshot()[-1]
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(app._clipboard, selected.text())

    async def test_escape_closes_the_overlay(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await self.open_log(app, pilot)
                await pilot.press("escape")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, NotificationLogScreen)

    async def test_opening_the_log_clears_the_unread_chip(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("broke", severity="error")
                await pilot.pause()
                self.assertEqual(app.query_one("#hints", Taskbar).log_count, 1)
                await self.open_log(app, pilot)
                await pilot.pause()
                self.assertEqual(app.notification_log.unread, 0)
                self.assertEqual(app.screen_stack[0].query_one("#hints", Taskbar).log_count, 0)

    async def test_the_newest_entries_are_visible_in_a_long_log(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 24)) as pilot:
                await pilot.pause()
                for index in range(30):
                    app.notify(f"message {index}")
                screen = await self.open_log(app, pilot)
                await pilot.pause()
                listing = screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.highlighted, 29)
                self.assertTrue(listing.scroll_offset.y > 0 or listing.is_vertical_scroll_end)

    async def test_a_message_arriving_while_open_appends_a_row(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("first")
                screen = await self.open_log(app, pilot)
                app.notify("second")
                await pilot.pause()
                texts = self.options(screen)
                self.assertEqual(len(texts), 2)
                self.assertIn("second", texts[-1])

    async def test_clicking_the_chip_opens_the_overlay(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("broke", severity="error")
                await pilot.pause()
                bar = app.query_one("#hints", Taskbar)
                await pilot.click(bar, offset=(bar._log_start + 1, 0))
                await pilot.pause()
                self.assertIsInstance(app.screen, NotificationLogScreen)
                self.assertEqual(app.notification_log.unread, 0)

    async def test_the_overlay_fits_a_narrow_terminal(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(40, 24)) as pilot:
                await pilot.pause()
                app.notify("careful", severity="warning")
                screen = await self.open_log(app, pilot)
                page = screen.query_one("#log-page")
                self.assertLessEqual(page.size.width, 40)
                listing = screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.option_count, 1)

    async def test_the_overlay_survives_a_resize(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("first")
                await self.open_log(app, pilot)
                await pilot.resize_terminal(40, 24)
                await pilot.pause()
                self.assertIsInstance(app.screen, NotificationLogScreen)
                listing = app.screen.query_one("#log-list", OptionList)
                self.assertEqual(listing.option_count, 1)


if __name__ == "__main__":
    unittest.main()
