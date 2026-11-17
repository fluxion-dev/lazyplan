"""The seeded log matrix: real notify call sites log, and nothing ordinary toasts."""

from __future__ import annotations

import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from textual.app import App
    from textual.widgets import OptionList

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.notification_log import NotificationLogScreen
    from lazyplan.presentation.tui.widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError as exc:  # pragma: no cover - textual not installed
    raise unittest.SkipTest(f"textual not installed: {exc}") from None

NO_UPDATE = mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"})
SEED = 31


class SeededLogMatrixTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_the_seeded_action_matrix_logs_and_never_toasts(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                calls = [
                    lambda: app.action_fold(),
                    lambda: app.action_fold_all(),
                    lambda: app.action_delete(),
                    lambda: app.action_edit_selection(),
                    lambda: app.action_add_criterion(),
                    lambda: app.action_export_md(),
                    lambda: app.action_new_milestone(),
                    lambda: app.action_toggle_status(),
                    lambda: app.action_claim_task(),
                    lambda: app.action_block_task(),
                    lambda: app.action_health_prompt(),
                ]
                random.Random(SEED).shuffle(calls)
                with mock.patch.object(App, "notify") as toast:
                    for call in calls:
                        before = len(app.notification_log)
                        call()
                        self.assertGreater(len(app.notification_log), before)
                toast.assert_not_called()
                await pilot.pause()
                self.assertEqual(app.notification_log.unread, 0)
                self.assertEqual(len(app._notifications), 0)

    async def test_the_seeded_exception_paths_are_the_only_toasts(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db, startup_notice="update failed: disk full")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.update_controller.announce("update available: v99.0.0", "99.0.0")
                await pilot.pause()
                messages = [entry.message for entry in app.notification_log.snapshot()]
                self.assertIn("update failed: disk full", messages)
                self.assertIn("update available: v99.0.0", messages)
                self.assertEqual(len(app._notifications), 2)

    async def test_the_matrix_chip_overlay_and_clear_hold_at_both_widths(self) -> None:
        for size in ((120, 40), (40, 24)):
            with self.subTest(size=size), NO_UPDATE:
                app = create_app(self.db)
                async with app.run_test(size=size) as pilot:
                    await pilot.pause()
                    app.notify("saved")
                    app.notify("careful", severity="warning")
                    app.notify("broke", severity="error")
                    await pilot.pause()
                    bar = app.query_one("#hints", Taskbar)
                    self.assertEqual(bar.log_count, 2)
                    self.assertIn("log 2", str(bar.render()))
                    app.action_notification_log()
                    await pilot.pause()
                    self.assertIsInstance(app.screen, NotificationLogScreen)
                    self.assertEqual(app.notification_log.unread, 0)
                    listing = app.screen.query_one("#log-list", OptionList)
                    self.assertEqual(listing.option_count, 3)
                    self.assertEqual(listing.highlighted, 2)
                    await pilot.press("y")
                    await pilot.pause()
                    self.assertTrue(app._clipboard)
                    await pilot.press("x")
                    await pilot.pause()
                    self.assertEqual(len(app.notification_log), 0)
                    await pilot.press("escape")
                    await pilot.pause()
                    self.assertNotIsInstance(app.screen, NotificationLogScreen)

    async def test_a_worker_notification_still_logs(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.run_worker(
                    lambda: app.notify("from a worker", severity="warning"),
                    thread=True,
                    group="matrix",
                )
                for _ in range(20):
                    await pilot.pause(0.05)
                    if app.notification_log.unread:
                        break
                self.assertEqual(app.notification_log.unread, 1)
                self.assertEqual(app.notification_log.snapshot()[-1].message, "from a worker")


if __name__ == "__main__":
    unittest.main()
