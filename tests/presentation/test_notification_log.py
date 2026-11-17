"""Notifications route into one bounded log; only startup and update notices toast."""

from __future__ import annotations

import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.presentation.tui.controllers.notifications import (
    BADGE_SEVERITIES,
    CAPACITY,
    NotificationEntry,
    NotificationLog,
)

try:
    from textual.app import App

    from lazyplan.presentation.tui import create_app

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - textual not installed
    _TEXTUAL_OK = False

CLOCK = re.compile(r"^\d{2}:\d{2}:\d{2}$")


class NotificationLogTest(unittest.TestCase):
    def test_an_append_stores_every_field(self) -> None:
        log = NotificationLog()
        entry = log.append("claimed T1", severity="warning", source="claims")
        self.assertIsInstance(entry, NotificationEntry)
        self.assertEqual(entry.message, "claimed T1")
        self.assertEqual(entry.severity, "warning")
        self.assertEqual(entry.source, "claims")
        self.assertRegex(entry.clock, CLOCK)
        self.assertEqual(log.snapshot(), (entry,))

    def test_entries_keep_append_order_oldest_first(self) -> None:
        log = NotificationLog()
        for index in range(3):
            log.append(f"m{index}")
        self.assertEqual([entry.message for entry in log.snapshot()], ["m0", "m1", "m2"])

    def test_the_log_keeps_the_last_500_entries(self) -> None:
        log = NotificationLog()
        for index in range(CAPACITY + 3):
            log.append(f"m{index}")
        entries = log.snapshot()
        self.assertEqual(len(entries), CAPACITY)
        self.assertEqual(log.capacity, CAPACITY)
        self.assertEqual(entries[0].message, "m3")
        self.assertEqual(entries[-1].message, f"m{CAPACITY + 2}")

    def test_only_unread_warnings_and_errors_count(self) -> None:
        log = NotificationLog()
        log.append("saved")
        log.append("careful", severity="warning")
        log.append("broke", severity="error")
        log.append("hint")
        self.assertEqual(log.unread, 2)
        self.assertEqual(BADGE_SEVERITIES, frozenset({"warning", "error"}))

    def test_mark_read_keeps_the_entries(self) -> None:
        log = NotificationLog()
        log.append("broke", severity="error")
        log.mark_read()
        self.assertEqual(log.unread, 0)
        self.assertEqual(len(log), 1)

    def test_clear_drops_the_entries_and_the_badge(self) -> None:
        log = NotificationLog()
        log.append("broke", severity="error")
        log.clear()
        self.assertEqual(log.snapshot(), ())
        self.assertEqual(log.unread, 0)

    def test_a_new_warning_after_mark_read_badges_again(self) -> None:
        log = NotificationLog()
        log.append("broke", severity="error")
        log.mark_read()
        log.append("broke again", severity="error")
        self.assertEqual(log.unread, 1)

    def test_entry_text_names_time_severity_message_and_source(self) -> None:
        log = NotificationLog(clock=lambda: 1_700_000_000.0)
        entry = log.append("copied SHA", severity="warning", source="source")
        text = entry.text()
        self.assertRegex(text, r"^\d{2}:\d{2}:\d{2}  warning      copied SHA")
        self.assertTrue(text.endswith("(source)"))

    def test_entry_text_without_a_source_has_no_parentheses(self) -> None:
        entry = NotificationLog().append("plain")
        self.assertNotIn("(", entry.text())

    def test_worker_threads_append_under_one_lock(self) -> None:
        log = NotificationLog()
        workers = [threading.Thread(target=log.append, args=(f"w{index}",)) for index in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(len(log), 4)
        self.assertEqual({entry.message for entry in log.snapshot()}, {f"w{i}" for i in range(4)})


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class NotificationRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def app(self):
        return create_app(self.db)

    def test_ordinary_notify_logs_without_reaching_textual(self) -> None:
        app = self.app()
        with mock.patch.object(App, "notify") as toast:
            app.notify("saved P1")
        toast.assert_not_called()
        entry = app.notification_log.snapshot()[-1]
        self.assertEqual(entry.message, "saved P1")
        self.assertEqual(entry.severity, "information")
        self.assertEqual(entry.source, "tree")

    def test_every_severity_is_logged_with_its_source(self) -> None:
        app = self.app()
        app.notify("note", source="hub")
        app.notify("careful", severity="warning", source="source")
        app.notify("broke", severity="error", source="setup")
        self.assertEqual(
            [(entry.severity, entry.source) for entry in app.notification_log.snapshot()],
            [("information", "hub"), ("warning", "source"), ("error", "setup")],
        )

    def test_notify_toast_logs_and_toasts_exactly_once(self) -> None:
        app = self.app()
        with mock.patch.object(App, "notify") as toast:
            app.notify_toast("update available", source="update")
        toast.assert_called_once()
        entry = app.notification_log.snapshot()[-1]
        self.assertEqual((entry.message, entry.source), ("update available", "update"))

    def test_the_default_source_is_the_tree_before_mount(self) -> None:
        app = self.app()
        app.notify("early")
        self.assertEqual(app.notification_log.snapshot()[-1].source, "tree")


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class NotificationToastPilotTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_an_ordinary_notify_raises_no_toast(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"}):
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.clear_notifications()
                app.notify("saved")
                await pilot.pause()
                self.assertEqual(len(app._notifications), 0)
                self.assertEqual(app.notification_log.snapshot()[-1].message, "saved")

    async def test_a_startup_notice_toasts_and_joins_the_log(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"}):
            app = create_app(self.db, startup_notice="update v9 installed")
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                self.assertEqual(len(app._notifications), 1)
                entry = app.notification_log.snapshot()[-1]
                self.assertEqual((entry.message, entry.source), ("update v9 installed", "startup"))

    async def test_an_update_notice_toasts_and_joins_the_log(self) -> None:
        with mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"}):
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                for _ in range(40):
                    if not app.update_controller.checking:
                        break
                    await pilot.pause(0.05)
                app.update_controller.stop()
                app.clear_notifications()
                app.update_controller.announce("update available: v99.0.0", "99.0.0")
                await pilot.pause()
                self.assertEqual(len(app._notifications), 1)
                entry = app.notification_log.snapshot()[-1]
                self.assertEqual(entry.source, "update")


if __name__ == "__main__":
    unittest.main()
