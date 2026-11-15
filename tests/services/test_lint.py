"""Plan lint rules, porcelain rows, and strict exit codes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services import lint
from lazyplan.store import Store
from tests.support.home import sandbox_home


class TestLint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "lint.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(
            milestone.id,
            "T",
            "Commit slice: one commit.\n\nVerification: pytest.",
            actor="fixture",
        )
        criterion = store.add_criteria("plan", plan.id, "Works", actor="fixture")
        store.relate_criterion(criterion.id, task.id, actor="fixture")
        self.store = store
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "alice", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_clean_plan_has_no_findings(self):
        self.assertEqual(lint.lint_plan(self.store, 1), [])

    def test_uncovered_criterion(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        self.assertIn("uncovered-criterion", [finding.rule for finding in findings])

    def test_missing_slice_verification_and_placeholder(self):
        task = self.store.add_task(1, "Vague", "TODO: something", actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        rules = {finding.rule for finding in findings if finding.obj_id == task.id}
        self.assertIn("missing-commit-slice", rules)
        self.assertIn("missing-verification", rules)
        self.assertIn("placeholder-text", rules)

    def test_done_rows_with_open_criteria(self):
        criterion = self.store.add_criteria("task", 1, "Open", actor="fixture")
        services.set_status(self.store, "task", 1, Status.DONE, actor="fixture")
        services.set_status(self.store, "plan", 1, Status.DONE, actor="fixture")
        findings = lint.lint_plan(self.store, 1)
        assert findings is not None
        self.assertIn(
            "done-with-open-criteria",
            [finding.rule for finding in findings],
        )
        self.assertTrue(criterion.done is False)

    def test_enforced_drift_is_an_error(self):
        self.store.add_revision(1, "a" * 64, "{}", enforced=True)
        self.store.update_task(1, title="Renamed", reason="rename")
        rules = [finding.rule for finding in lint.lint_plan(self.store, 1)]
        self.assertIn("enforced-drift", rules)
        self.assertNotIn("enforced-drift-no-reason", rules)

    def test_advisory_drift_is_not_a_lint_error(self):
        self.store.add_revision(1, "a" * 64, "{}")
        self.store.update_task(1, title="Renamed", reason="rename")
        self.assertEqual(lint.lint_plan(self.store, 1), [])

    def test_enforced_drift_without_reason_is_an_error(self):
        self.store.add_revision(1, "a" * 64, "{}", enforced=True)
        self.store.update_task(1, title="Renamed")
        rules = [finding.rule for finding in lint.lint_plan(self.store, 1)]
        self.assertIn("enforced-drift", rules)
        self.assertIn("enforced-drift-no-reason", rules)

    def test_cli_strict_fails_on_enforced_drift(self):
        self.store.add_revision(1, "a" * 64, "{}", enforced=True)
        self.store.update_task(1, title="Renamed", reason="rename")
        code, out, _err = self._run("lint", "--plan", "1", "--strict")
        self.assertEqual(code, 2)
        self.assertIn("enforced-drift", out)

    def _lane_rules(self, plan_id: int) -> list[str]:
        findings = lint.lint_plan(self.store, plan_id)
        assert findings is not None
        return [
            finding.rule
            for finding in findings
            if finding.rule.startswith(("lane-", "parallel-", "missing-integrator", "integrator-"))
        ]

    def test_parallel_plan_needs_a_lane_cap_and_two_lanes(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=1)
        milestone = self.store.add_milestone(plan.id, "Only")
        task = self.store.add_task(milestone.id, "Do", "Commit: one.\n\nVerify: tests.", role="qa")
        self.assertIn("parallel-cap", self._lane_rules(plan.id))
        self.assertIn("parallel-lanes", self._lane_rules(plan.id))
        self.assertTrue(task.id)

    def test_parallel_plan_needs_an_integrator_lane(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=2)
        for title in ("A", "B"):
            milestone = self.store.add_milestone(plan.id, title, lane_group=1)
            self.store.add_task(
                milestone.id, f"Work {title}", "Commit: one.\n\nVerify: tests.", role="qa"
            )
        rules = self._lane_rules(plan.id)
        self.assertIn("missing-integrator", rules)

    def test_integrator_lane_runs_after_the_lanes_it_merges(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=2)
        integrator = self.store.add_milestone(
            plan.id, "Integrate", lane_group=1, agent_role="integrator"
        )
        self.store.add_task(integrator.id, "Merge", "Commit: one.\n\nVerify: tests.")
        for title in ("A", "B"):
            milestone = self.store.add_milestone(plan.id, title, lane_group=2)
            self.store.add_task(
                milestone.id, f"Work {title}", "Commit: one.\n\nVerify: tests.", role="qa"
            )
        self.assertIn("integrator-order", self._lane_rules(plan.id))

    def test_same_wave_lanes_must_not_share_touchpoints(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=2)
        for title, path in (("A", "src/**"), ("B", "src/lazyplan/**")):
            milestone = self.store.add_milestone(plan.id, title, lane_group=1)
            task = self.store.add_task(
                milestone.id, f"Work {title}", "Commit: one.\n\nVerify: tests.", role="qa"
            )
            self.store.add_touchpoint(task.id, path)
        self.assertIn("lane-touchpoint-overlap", self._lane_rules(plan.id))

    def test_lane_qa_coverage_when_qa_is_present(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=2)
        first = self.store.add_milestone(plan.id, "A", lane_group=1)
        self.store.add_task(first.id, "Work A", "Commit: one.\n\nVerify: tests.", role="qa")
        second = self.store.add_milestone(plan.id, "B", lane_group=1)
        self.store.add_task(second.id, "Work B", "Commit: one.\n\nVerify: tests.")
        self.assertIn("lane-missing-qa", self._lane_rules(plan.id))

    def test_clean_parallel_plan_has_no_lane_findings(self):
        plan = self.store.add_plan("P2", dispatch_mode="parallel", max_agents=2)
        for title in ("A", "B"):
            milestone = self.store.add_milestone(plan.id, title, lane_group=1)
            self.store.add_task(
                milestone.id, f"Work {title}", "Commit: one.\n\nVerify: tests.", role="qa"
            )
        integrator = self.store.add_milestone(
            plan.id, "Integrate", lane_group=2, agent_role="integrator"
        )
        self.store.add_task(integrator.id, "Merge", "Commit: one.\n\nVerify: tests.")
        self.assertEqual(self._lane_rules(plan.id), [])

    def test_serial_plan_is_free_of_lane_findings(self):
        self.assertEqual(self._lane_rules(1), [])

    def test_cli_text_and_strict_exit(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        code, out, err = self._run("lint", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("uncovered-criterion", out)
        code, out, err = self._run("lint", "--plan", "1", "--strict")
        self.assertEqual(code, 2)

    def test_cli_porcelain_and_json(self):
        self.store.add_criteria("plan", 1, "Fast", actor="fixture")
        code, out, err = self._run("--porcelain", "lint", "--plan", "1")
        self.assertEqual(code, 0, err)
        row = out.rstrip("\n").split("\t")
        self.assertEqual(row[:3], ["lint", "uncovered-criterion", "error"])
        self.assertEqual(row[4], "criterion:2")
        code, out, err = self._run("--json", "lint", "--plan", "1")
        payload = json.loads(out)
        self.assertEqual(payload[0]["rule"], "uncovered-criterion")

    def test_missing_plan_exits_one(self):
        code, out, err = self._run("lint", "--plan", "99")
        self.assertEqual(code, 1)
        self.assertIn("plan 99", err)


if __name__ == "__main__":
    unittest.main()
