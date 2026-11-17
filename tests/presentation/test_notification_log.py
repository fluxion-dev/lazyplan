"""The notification log keeps the last 500 entries and counts unread warnings."""

from __future__ import annotations

import re
import threading
import unittest

from lazyplan.presentation.tui.controllers.notifications import (
    BADGE_SEVERITIES,
    CAPACITY,
    NotificationEntry,
    NotificationLog,
)

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


if __name__ == "__main__":
    unittest.main()
