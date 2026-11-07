"""CLI approval, revision history, and drift reports."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class PlanRevisionsCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Demo", description="what", goal="why")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _approve(self, *extra: str) -> tuple[int, str, str]:
        return self._run("--json", "plan", "approve", "--id", str(self.plan.id), *extra)

    def test_approve_json_and_noop(self) -> None:
        code, out, err = self._approve("--reason", "initial")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["revision"]["revision"], 1)
        self.assertNotIn("snapshot", payload["revision"])
        again = self._approve()
        self.assertEqual(again[0], 0, again[2])
        self.assertFalse(json.loads(again[1])["created"])

    def test_approve_policy_change(self) -> None:
        self._approve()
        code, out, err = self._approve("--enforce")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["revision"]["revision"], 2)
        self.assertTrue(payload["revision"]["enforced"])

    def test_reapproval_with_drift_needs_reason(self) -> None:
        self._approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        code, _out, err = self._approve()
        self.assertEqual(code, 2)
        self.assertIn("reason", err)
        code, out, err = self._approve("--reason", "accept rename")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["revision"]["revision"], 2)
        self.assertEqual(payload["acknowledged"], 1)

    def test_revisions_json_and_text(self) -> None:
        self._approve("--reason", "initial")
        code, out, err = self._run("--json", "plan", "revisions", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload[0]["revision"], 1)
        self.assertEqual(payload[0]["changes"], 0)
        code, out, err = self._run("plan", "revisions", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("r1", out)
        self.assertIn("initial", out)

    def test_diff_json_reports_reason_and_check(self) -> None:
        self._approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        code, out, err = self._run("--json", "plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["drifted"])
        self.assertEqual(payload["changes"][0]["field"], "title")
        self.assertEqual(payload["changes"][0]["reason"], "rename")
        self.assertNotIn("snapshot", payload["from"])
        code, _out, _err = self._run("plan", "diff", "--id", str(self.plan.id), "--check")
        self.assertEqual(code, 1)

    def test_diff_check_passes_in_sync(self) -> None:
        self._approve()
        code, _out, _err = self._run("plan", "diff", "--id", str(self.plan.id), "--check")
        self.assertEqual(code, 0)

    def test_diff_text_and_porcelain(self) -> None:
        self._approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        code, out, err = self._run("plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("scope change", out)
        self.assertIn("T1", out)
        self.assertIn("reason: rename", out)
        code, out, err = self._run("--porcelain", "plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.splitlines()]
        self.assertEqual(rows[0][0], "drift")
        self.assertEqual(rows[0][2], "change")
        self.assertEqual(rows[1][2], "drift")

    def test_diff_stored_revisions(self) -> None:
        self._approve()
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        self._approve("--reason", "accept rename")
        code, out, err = self._run(
            "--json",
            "plan",
            "diff",
            "--id",
            str(self.plan.id),
            "--from",
            "1",
            "--to",
            "2",
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["drifted"])
        self.assertEqual(payload["to"]["revision"], 2)
        self.assertEqual(payload["changes"][0]["reason"], "")

    def test_diff_without_approval_is_an_error(self) -> None:
        code, _out, err = self._run("plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 2)
        self.assertIn("no approved revision", err)

    def test_invalid_to_and_unknown_plan(self) -> None:
        self._approve()
        code, _out, err = self._run("plan", "diff", "--id", str(self.plan.id), "--to", "nope")
        self.assertEqual(code, 2)
        self.assertIn("--to", err)
        code, _out, _err = self._run("plan", "diff", "--id", "999")
        self.assertEqual(code, 1)

    def test_no_revisions_text(self) -> None:
        code, out, err = self._run("plan", "revisions", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("no approved revision", out)

    def test_scope_reasons_are_recorded(self) -> None:
        self._approve()
        code, _out, err = self._run(
            "task", "edit", "--id", str(self.task.id), "--title", "Renamed", "--reason", "clarify"
        )
        self.assertEqual(code, 0, err)
        code, out, err = self._run("--json", "plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["changes"][0]["reason"], "clarify")

        code, _out, err = self._run(
            "plan", "edit", "--id", str(self.plan.id), "--what", "new what", "--reason", "narrow"
        )
        self.assertEqual(code, 0, err)
        code, out, err = self._run("--json", "plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertIn(
            ("what", "narrow"),
            [(item["field"], item["reason"]) for item in payload["changes"]],
        )

    def test_missing_reason_is_reported(self) -> None:
        self._approve()
        code, _out, err = self._run("task", "edit", "--id", str(self.task.id), "--title", "Renamed")
        self.assertEqual(code, 0, err)
        code, out, err = self._run("--json", "plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["changes"][0]["reason"], "")
        code, out, err = self._run("plan", "diff", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("no reason", out)

    def test_criterion_and_milestone_reasons_are_recorded(self) -> None:
        self._approve()
        code, out, err = self._run(
            "--json",
            "criterion",
            "add",
            "--kind",
            "plan",
            "--id",
            str(self.plan.id),
            "--text",
            "New proof",
            "--reason",
            "add proof",
        )
        self.assertEqual(code, 0, err)
        criterion_id = json.loads(out)["criteria"]["id"]
        code, _out, err = self._run(
            "milestone",
            "add",
            "--plan",
            str(self.plan.id),
            "--title",
            "M2",
            "--reason",
            "new slice",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self._run(
            "criterion", "delete", "--id", str(criterion_id), "--reason", "wrong proof"
        )
        self.assertEqual(code, 0, err)
        changes = self.store.list_plan_changes(self.plan.id)
        reasons = [(item.kind, item.action, item.reason) for item in changes]
        self.assertIn(("criterion", "add", "add proof"), reasons)
        self.assertIn(("milestone", "add", "new slice"), reasons)
        self.assertIn(("criterion", "delete", "wrong proof"), reasons)

    def test_plan_reads_include_approval_state(self) -> None:
        self._approve("--reason", "initial")
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        code, out, err = self._run("--json", "plan", "show", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["approval"]["revision"], 1)
        self.assertEqual(payload["approval"]["drift"], 1)
        code, out, err = self._run("--json", "plan", "list", "--tree")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload[0]["approval"]["revision"], 1)

    def test_enforced_plan_done_gate(self) -> None:
        plan = self.store.add_plan("Gate")
        code, _out, err = self._run("--json", "plan", "approve", "--id", str(plan.id), "--enforce")
        self.assertEqual(code, 0, err)
        self._run("plan", "edit", "--id", str(plan.id), "--what", "new scope", "--reason", "narrow")
        code, _out, err = self._run("plan", "move", "--id", str(plan.id), "--to", "done")
        self.assertEqual(code, 2)
        self.assertIn("scope change", err)
        self.assertNotEqual(self.store.get_plan(plan.id).status.value, "done")
        code, _out, err = self._run(
            "plan",
            "move",
            "--id",
            str(plan.id),
            "--to",
            "done",
            "--override",
            "ship now",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.get_plan(plan.id).status.value, "done")
        notes = self.store.list_notes("plan", plan.id)
        self.assertTrue(any("Drift override" in note.text for note in notes))

    def test_advisory_plan_done_is_not_gated(self) -> None:
        plan = self.store.add_plan("Advisory")
        self._run("--json", "plan", "approve", "--id", str(plan.id))
        self._run("plan", "edit", "--id", str(plan.id), "--what", "new scope", "--reason", "narrow")
        code, _out, err = self._run("plan", "move", "--id", str(plan.id), "--to", "done")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.store.get_plan(plan.id).status.value, "done")

    def test_approve_text(self) -> None:
        code, out, err = self._run("plan", "approve", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn(f"approved P{self.plan.id} r1", out)
        code, out, err = self._run("plan", "approve", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        self.assertIn("already approved at r1", out)

    def test_porcelain_approve(self) -> None:
        code, out, err = self._run("--porcelain", "plan", "approve", "--id", str(self.plan.id))
        self.assertEqual(code, 0, err)
        fields = out.split("\t")
        self.assertEqual(fields[0], "plan")
        self.assertEqual(fields[2], "approved")


if __name__ == "__main__":
    unittest.main()
