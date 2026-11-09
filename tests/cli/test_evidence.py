"""Criterion proof and evidence CLI."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class EvidenceCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("P")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.task = self.store.add_task(self.milestone.id, "T")
        self.criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.relate_criterion(self.criterion.id, self.task.id)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _prove(self, *extra: str) -> tuple[int, str, str]:
        return self._run(
            "--json",
            "criterion",
            "prove",
            "--id",
            str(self.criterion.id),
            *extra,
        )

    def test_passing_proof_records_and_lists(self) -> None:
        code, out, err = self._prove("--command", "pytest", "--exit-code", "0")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertFalse(payload["criterion"]["done"])
        self.assertEqual(payload["evidence"]["command"], "pytest")

        code, out, err = self._run(
            "--json", "criterion", "evidence", "--id", str(self.criterion.id)
        )
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual(rows[0]["command"], "pytest")

    def test_failing_proof_leaves_open(self) -> None:
        code, out, err = self._prove("--command", "pytest", "--exit-code", "1")
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertFalse(payload["criterion"]["done"])

    def test_edit_sets_and_clears_completion(self) -> None:
        code, out, err = self._run(
            "--json", "criterion", "edit", "--id", str(self.criterion.id), "--done"
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["criteria"]["done"])
        self.assertTrue(self.store.get_criterion(self.criterion.id).done)
        code, out, err = self._run(
            "--json", "criterion", "edit", "--id", str(self.criterion.id), "--open"
        )
        self.assertEqual(code, 0, err)
        self.assertFalse(json.loads(out)["criteria"]["done"])
        self.assertFalse(self.store.get_criterion(self.criterion.id).done)

    def test_edit_requires_a_change(self) -> None:
        code, _out, err = self._run("criterion", "edit", "--id", str(self.criterion.id))
        self.assertEqual(code, 2)
        self.assertIn("--text", err)

    def test_text_and_porcelain_output(self) -> None:
        code, out, err = self._run(
            "criterion", "prove", "--id", str(self.criterion.id), "--command", "pytest"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("recorded pass evidence", out)
        code, out, err = self._run("criterion", "evidence", "--id", str(self.criterion.id))
        self.assertEqual(code, 0, err)
        self.assertIn("pytest", out)
        code, out, err = self._run(
            "--porcelain",
            "criterion",
            "prove",
            "--id",
            str(self.criterion.id),
            "--command",
            "pytest",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split("\t")[0], "evidence")

    def test_empty_evidence_is_an_error(self) -> None:
        code, _out, err = self._prove()
        self.assertEqual(code, 2)
        self.assertIn("command", err)

    def test_unrelated_task_is_an_error(self) -> None:
        other = self.store.add_task(self.milestone.id, "Other")
        code, _out, err = self._prove("--command", "pytest", "--task", str(other.id))
        self.assertEqual(code, 2)
        self.assertIn("not linked", err)

    def test_evidence_list_empty_state(self) -> None:
        code, out, err = self._run("criterion", "evidence", "--id", str(self.criterion.id))
        self.assertEqual(code, 0, err)
        self.assertIn("no evidence", out)

    def test_trace_includes_evidence(self) -> None:
        self._prove("--command", "pytest", "--exit-code", "0")
        code, out, err = self._run("trace", "--criterion", str(self.criterion.id))
        self.assertEqual(code, 0, err)
        self.assertIn("evidence", out)
        self.assertIn("pytest", out)
        code, out, err = self._run("--porcelain", "trace", "--criterion", str(self.criterion.id))
        self.assertEqual(code, 0, err)
        self.assertTrue(any(line.startswith("evidence\t") for line in out.splitlines()))

    def test_task_finish_requires_evidence(self) -> None:
        code, _out, err = self._run(
            "task", "finish", "--id", str(self.task.id), "--require-evidence"
        )
        self.assertEqual(code, 2)
        self.assertIn("needs passing evidence", err)

    def test_audit_min_evidence_gates(self) -> None:
        code, _out, err = self._run(
            "audit", "--plan", str(self.plan.id), "--strict", "--min-evidence", "0.8"
        )
        self.assertEqual(code, 2)
        self.assertIn("evidence", _out + err)
        self._prove("--command", "pytest", "--exit-code", "0")
        code, out, err = self._run(
            "--json", "audit", "--plan", str(self.plan.id), "--strict", "--min-evidence", "0.8"
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["evidence_covered"], 1)
        self.assertEqual(payload["evidence_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
