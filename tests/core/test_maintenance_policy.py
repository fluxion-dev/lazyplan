"""Pure maintenance policy and port results."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Claim, Plan, Session, Status
from lazyplan.core.policies.maintenance import (
    DEFAULT_WINDOW_SECS,
    check_archive_mode,
    event_cutoff,
    is_archived_row,
    is_done_past_window,
    is_ended_past_window,
    is_expired_claim,
    is_old_event,
    parse_window_days,
    parse_window_secs,
    plan_archive_candidates,
    session_archive_candidates,
    visible_rows,
)
from lazyplan.core.ports.maintenance import (
    ArchiveResult,
    BackupResult,
    MaintenanceReport,
    TableBytes,
    TableCount,
    TrimResult,
    VacuumResult,
)


class TestWindowParsing(unittest.TestCase):
    def test_named_and_bare_day_counts(self) -> None:
        self.assertEqual(parse_window_days("7.days"), 7.0)
        self.assertEqual(parse_window_days("30.days"), 30.0)
        self.assertEqual(parse_window_days("14"), 14.0)
        self.assertEqual(parse_window_days("2.weeks"), 14.0)
        self.assertEqual(parse_window_secs("1.day"), 86400.0)

    def test_empty_input_uses_the_one_week_default(self) -> None:
        self.assertEqual(parse_window_days(None), 7.0)
        self.assertEqual(parse_window_days("  "), 7.0)
        self.assertEqual(parse_window_secs(None), DEFAULT_WINDOW_SECS)

    def test_zero_negative_and_unknown_units_are_rejected(self) -> None:
        for text in ("0", "0.days", "-3", "-1.days", "7.hours", "week", "1..days"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_window_days(text)


class TestArchiveMode(unittest.TestCase):
    def test_modes_and_rejection(self) -> None:
        self.assertEqual(check_archive_mode("hide"), "hide")
        self.assertEqual(check_archive_mode("only"), "only")
        self.assertEqual(check_archive_mode("show"), "show")
        with self.assertRaises(ValueError):
            check_archive_mode("all")

    def test_visible_rows_filters_by_stamp(self) -> None:
        live = Plan(id=1, name="Live")
        archived = Plan(id=2, name="Archived", archived_at=10.0)
        rows = [live, archived]
        self.assertEqual(visible_rows(rows), [live])
        self.assertEqual(visible_rows(rows, "only"), [archived])
        self.assertEqual(visible_rows(rows, "show"), rows)
        self.assertTrue(is_archived_row(archived))
        self.assertFalse(is_archived_row(live))


class TestCandidates(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 1_000_000.0
        self.done = Plan(id=1, name="Done", status=Status.DONE)
        self.events = {1: (self.now - DEFAULT_WINDOW_SECS - 1, "done")}

    def test_done_plan_past_the_window(self) -> None:
        self.assertTrue(is_done_past_window(self.done, self.events, self.now))
        self.assertEqual(plan_archive_candidates([self.done], self.events, self.now), [self.done])
        self.assertFalse(is_done_past_window(self.done, {}, self.now))
        self.assertFalse(is_done_past_window(self.done, {1: (0.0, "doing")}, self.now))

    def test_open_and_fresh_plans_are_not_candidates(self) -> None:
        fresh = Plan(id=2, name="Fresh", status=Status.DONE)
        events = {2: (self.now - 10, "done")}
        doing = Plan(id=3, name="Doing", status=Status.DOING)
        self.assertEqual(plan_archive_candidates([fresh, doing], events, self.now), [])

    def test_already_archived_plans_are_not_candidates(self) -> None:
        archived = Plan(id=1, name="Done", status=Status.DONE, archived_at=1.0)
        self.assertEqual(plan_archive_candidates([archived], self.events, self.now), [])

    def test_ended_sessions_past_the_window(self) -> None:
        old = Session(id=1, ended_at=self.now - DEFAULT_WINDOW_SECS - 1)
        fresh = Session(id=2, ended_at=self.now - 10)
        open_row = Session(id=3)
        archived = Session(id=4, ended_at=self.now - DEFAULT_WINDOW_SECS - 1, archived_at=1.0)
        self.assertTrue(is_ended_past_window(old, self.now))
        self.assertFalse(is_ended_past_window(open_row, self.now))
        self.assertEqual(
            session_archive_candidates([old, fresh, open_row, archived], self.now), [old]
        )

    def test_expired_claim(self) -> None:
        claim = Claim(task_id=1, actor="ana", started_at=0.0, expires_at=10.0)
        self.assertTrue(is_expired_claim(claim, 10.0))
        self.assertTrue(is_expired_claim(claim, 11.0))
        self.assertFalse(is_expired_claim(claim, 9.0))

    def test_old_events(self) -> None:
        cutoff = event_cutoff(self.now)
        self.assertTrue(is_old_event({"ts": self.now - DEFAULT_WINDOW_SECS - 1}, cutoff))
        self.assertFalse(is_old_event({"ts": self.now}, cutoff))
        self.assertFalse(is_old_event({}, cutoff))


class TestPortResults(unittest.TestCase):
    def test_reports_serialize(self) -> None:
        report = MaintenanceReport(
            tables=(TableBytes("plans", 100, 2),),
            total_bytes=100,
            free_bytes=20,
            reclaimable_bytes=20,
        )
        self.assertEqual(report.to_dict()["tables"][0]["table"], "plans")
        trim = TrimResult(tables=(TableCount("events", 3),), applied=True)
        self.assertEqual(trim.total_rows, 3)
        self.assertTrue(trim.to_dict()["applied"])
        archive = ArchiveResult(plans=(1,), sessions=(2,), applied=False)
        self.assertEqual(archive.total, 2)
        vacuum = VacuumResult(before_bytes=100, after_bytes=40)
        self.assertEqual(vacuum.freed_bytes, 60)
        backup = BackupResult(path="snap.db", bytes=10, verified=True)
        self.assertTrue(backup.to_dict()["verified"])


if __name__ == "__main__":
    unittest.main()
