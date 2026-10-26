"""Audit metric model: coverage, status lag, and criteria gaps."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import audit, services  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class AuditCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "lazyplan.db")
        self.plan = self.store.add_plan("P", "what", goal="why")
        self.milestone = self.store.add_milestone(self.plan.id, "M", "desc")
        self.task = self.store.add_task(self.milestone.id, "T", "desc")

    def tearDown(self):
        self.tmp.cleanup()

    def _at(self, when: float, action):
        with mock.patch("lazyplan.store.time.time", return_value=when):
            action()

    def _status(self, when: float, status: Status) -> None:
        self._at(
            when,
            lambda: services.set_status(self.store, "task", self.task.id, status, actor="t"),
        )

    def _link(self, sha: str, when: float, task_id: int | None = None) -> None:
        self.store.link_commit(
            "task",
            task_id or self.task.id,
            sha,
            subject="work",
            timestamp=int(when),
            actor="t",
        )

    def test_coverage_counts_linked_non_merge_commits(self):
        self._link("a" * 40, 1000)
        commits = [
            audit.Commit("a" * 40, 1000, "/r", 1),
            audit.Commit("b" * 40, 1010, "/r", 1),
            audit.Commit("c" * 40, 1020, "/r", 2),
        ]
        result = audit.compute(self.store, [self.plan.id], commits)
        self.assertEqual(result.commits_total, 2)
        self.assertEqual(result.commits_linked, 1)
        self.assertAlmostEqual(result.coverage, 0.5)

    def test_lag_uses_first_status_after_the_commit(self):
        self._link("a" * 40, 1000)
        self._status(1060, Status.DOING)
        self._status(1120, Status.DONE)
        commits = [
            audit.Commit("a" * 40, 1000, "/r", 1),
            audit.Commit("b" * 40, 1050, "/r", 1),
        ]
        result = audit.compute(self.store, [self.plan.id], commits)
        self.assertEqual(result.lag_commits, [1.0])
        self.assertEqual(result.median_lag_minutes, 1.0)
        self.assertEqual(result.unresolved, 0)

    def test_unresolved_when_no_status_follows(self):
        self._link("a" * 40, 1000)
        result = audit.compute(self.store, [self.plan.id], [audit.Commit("a" * 40, 1000, "/r", 1)])
        self.assertEqual(result.unresolved, 1)
        self.assertEqual(result.lag_commits, [])

    def test_trace_coverage_tracks_plan_criteria(self):
        covered = self.store.add_criteria("plan", self.plan.id, "covered")
        self.store.add_criteria("plan", self.plan.id, "uncovered")
        self.store.relate_criterion(covered.id, self.task.id)
        result = audit.compute(self.store, [self.plan.id], [])
        self.assertEqual(result.criteria_total, 2)
        self.assertEqual(result.criteria_linked, 1)
        self.assertAlmostEqual(result.trace_coverage, 0.5)
        self.assertEqual([gap.id for gap in result.trace_gaps], [2])

    def test_min_trace_threshold_is_opt_in(self):
        self.store.add_criteria("plan", self.plan.id, "uncovered")
        result = audit.compute(self.store, [self.plan.id], [])
        self.assertEqual(audit.Thresholds().breaches(result), [])
        breaches = audit.Thresholds(trace=0.8).breaches(result)
        self.assertEqual(len(breaches), 1)
        self.assertIn("trace 0% < 80%", breaches[0])

    def test_gaps_only_on_done_rows(self):
        self.store.add_criteria("plan", self.plan.id, "plan gap")
        self.store.add_criteria("task", self.task.id, "task gap")
        self._at(2000, lambda: services.set_status(self.store, "plan", self.plan.id, Status.DONE))
        self._at(2001, lambda: services.set_status(self.store, "task", self.task.id, Status.DONE))
        gaps = audit.compute(self.store, [self.plan.id], []).gaps
        kinds = {(gap.kind, gap.text) for gap in gaps}
        self.assertIn(("plan", "plan gap"), kinds)
        self.assertIn(("task", "task gap"), kinds)

    def test_open_task_with_open_criteria_is_not_a_gap(self):
        self.store.add_criteria("task", self.task.id, "not yet")
        self.assertEqual(audit.compute(self.store, [self.plan.id], []).gaps, [])

    def test_gaps_ignore_rows_closed_before_the_window(self):
        self.store.add_criteria("task", self.task.id, "old debt")
        self._at(1000, lambda: services.set_status(self.store, "task", self.task.id, Status.DONE))
        self._at(
            1001,
            lambda: services.set_status(self.store, "milestone", self.milestone.id, Status.DONE),
        )
        self._at(1002, lambda: services.set_status(self.store, "plan", self.plan.id, Status.DONE))
        self.assertEqual(audit.compute(self.store, [self.plan.id], [], since=2000).gaps, [])
        self.assertEqual(len(audit.compute(self.store, [self.plan.id], [], since=500).gaps), 1)

    def test_empty_store_scores_perfect_coverage(self):
        empty = Store(Path(self.tmp.name) / "empty.db")
        result = audit.compute(empty, [], [])
        self.assertEqual(result.coverage, 1.0)
        self.assertEqual(result.commits_total, 0)

    def test_parse_since_units_and_iso(self):
        self.assertIsNone(audit.parse_since(""))
        self.assertIsNotNone(audit.parse_since("7.days"))
        self.assertIsNotNone(audit.parse_since("2026-10-01"))
        self.assertIsNone(audit.parse_since("tomorrow"))

    def test_plan_start_reads_the_add_event(self):
        self.assertIsNotNone(audit.plan_start(self.store, self.plan.id))

    def test_since_scopes_plans_to_recent_or_doing(self):
        store = Store(Path(self.tmp.name) / "window.db")
        with mock.patch("lazyplan.store.time.time", return_value=1000):
            old = store.add_plan("old")
        with mock.patch("lazyplan.store.time.time", return_value=3000):
            new = store.add_plan("new")
        result = audit.report(store, since=2000, cwd=self.tmp.name)
        self.assertEqual(result.plans, [new.id])
        self.assertNotIn(old.id, result.plans)

    def test_stale_link_does_not_break_the_sample(self):
        self._link("f" * 40, 1000)
        result = audit.compute(self.store, [self.plan.id], [])
        self.assertEqual(result.commits_total, 0)
        self.assertEqual(result.coverage, 1.0)

    def test_compute_does_not_write(self):
        before = self.store.path.read_bytes()
        audit.compute(self.store, [self.plan.id], [])
        self.assertEqual(self.store.path.read_bytes(), before)


class ThresholdCase(unittest.TestCase):
    def test_breaches_name_each_metric(self):
        result = audit.Report(commits_total=10, commits_linked=5, gaps=[audit.Gap("task", 1, "x")])
        reasons = audit.Thresholds().breaches(result)
        self.assertEqual(len(reasons), 2)
        self.assertIn("coverage", reasons[0])
        self.assertIn("open criteria", reasons[1])

    def test_clean_report_passes(self):
        self.assertEqual(audit.Thresholds().breaches(audit.Report()), [])


if __name__ == "__main__":
    unittest.main()
