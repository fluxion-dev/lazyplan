"""CLI plan apply: atomic writes, dry-run, retries, and key conflicts."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


def document(key: str = "demo", milestone_key: str = "build") -> dict:
    return {
        "plan": {
            "key": key,
            "title": "Demo plan",
            "why": "Why this matters.",
            "what": "## Scope\n\n- One thing.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": milestone_key,
                "title": "Build it",
                "desc": (
                    "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
                    "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
                    "Inputs: The approved definition and the scouted code path.\n\n"
                    "Slices: Implement, test, and document in separate green commits."
                ),
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": (
                            "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
                            "Touch: src/app.py\n\n"
                            "Inputs: The approved definition; none beyond the plan scope.\n\n"
                            "Commit: One implementation slice.\n\n"
                            "Verify: The relevant test suite passes.\n\n"
                            "Guardrails: Keep behavior outside the reviewed scope unchanged."
                        ),
                    },
                    {
                        "key": "qa",
                        "title": "Test it",
                        "desc": (
                            "Approach: Cover each acceptance criterion and edge case.\n\n"
                            "Touch: tests/test_app.py\n\n"
                            "Inputs: The implementation slice and the acceptance criteria.\n\n"
                            "Commit: One test slice.\n\n"
                            "Verify: The new tests pass.\n\n"
                            "Guardrails: Do not weaken existing assertions."
                        ),
                    },
                ],
            },
            {
                "key": "ship",
                "title": "Ship it",
                "desc": (
                    "Outcome: As a user, I want the release, so that the change ships.\n\n"
                    "Scope: In scope: the release notes and commands. Out of scope: new code.\n\n"
                    "Inputs: The green implementation and its verification commands.\n\n"
                    "Slices: Document the release in one green commit."
                ),
                "tasks": [
                    {
                        "key": "docs",
                        "title": "Document it",
                        "desc": (
                            "Approach: Document the shipped behavior where users look.\n\n"
                            "Touch: docs/\n\n"
                            "Inputs: The final implementation and its verification commands.\n\n"
                            "Commit: One documentation slice.\n\n"
                            "Verify: Links and examples resolve.\n\n"
                            "Guardrails: Do not document behavior the change did not ship."
                        ),
                    }
                ],
            },
        ],
    }


class PlanApplyCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.path = Path(self.tmp.name) / "plan.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_apply_creates_the_whole_tree(self):
        self._write(document())
        code, out, err = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["created"])
        self.assertEqual(payload["counts"], {"milestones": 2, "tasks": 3, "criteria": 2})
        store = Store(self.db)
        self.assertEqual(store.counts()["plans"], 1)
        self.assertEqual(store.counts()["tasks"], 3)
        self.assertEqual(store.get_entity_key("plan", "demo"), payload["plan"]["id"])
        self.assertIsNotNone(store.get_entity_key("milestone", "build"))
        self.assertIsNotNone(store.get_entity_key("task", "docs"))

    def test_dry_run_writes_nothing(self):
        self._write(document())
        code, out, err = self._run(
            "--json",
            "plan",
            "apply",
            "--direct",
            "--reason",
            "fixture",
            "--file",
            str(self.path),
            "--dry-run",
        )
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["created"])
        self.assertEqual(payload["milestones"][0]["tasks"][0]["key"], "impl")
        self.assertEqual(Store(self.db).counts()["plans"], 0)

    def test_retry_is_a_no_op(self):
        self._write(document())
        first = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        second = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(first[0], 0)
        self.assertEqual(second[0], 0)
        payload = json.loads(second[1])
        self.assertFalse(payload["created"])
        store = Store(self.db)
        self.assertEqual(store.counts()["plans"], 1)
        self.assertEqual(store.counts()["tasks"], 3)

    def test_invalid_document_leaves_zero_rows(self):
        payload = document()
        del payload["milestones"][0]["tasks"][0]["title"]
        self._write(payload)
        code, _out, err = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(code, 2)
        self.assertIn("title", err)
        self.assertEqual(Store(self.db).counts()["plans"], 0)

    def test_unknown_field_is_rejected(self):
        payload = document()
        payload["plan"]["owner"] = "someone"
        self._write(payload)
        code, _out, err = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown field", err)
        self.assertEqual(Store(self.db).counts()["plans"], 0)

    def test_key_conflict_rolls_back_the_new_plan(self):
        self._write(document())
        self.assertEqual(
            self._run(
                "--json",
                "plan",
                "apply",
                "--direct",
                "--reason",
                "fixture",
                "--file",
                str(self.path),
            )[0],
            0,
        )
        self._write(document(key="other", milestone_key="build"))
        code, _out, err = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(code, 2)
        self.assertIn("already belongs", err)
        store = Store(self.db)
        self.assertEqual(store.counts()["plans"], 1)
        self.assertIsNone(store.get_entity_key("plan", "other"))

    def test_porcelain_rows(self):
        self._write(document())
        code, out, err = self._run(
            "--porcelain",
            "plan",
            "apply",
            "--direct",
            "--reason",
            "fixture",
            "--file",
            str(self.path),
            "--dry-run",
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("plan\t-\tdry-run\tDemo plan\t-\t2/3"))
        code, out, err = self._run(
            "--porcelain",
            "plan",
            "apply",
            "--direct",
            "--reason",
            "fixture",
            "--file",
            str(self.path),
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("plan\t"))

    def test_missing_file(self):
        code, _out, err = self._run(
            "--json", "plan", "apply", "--direct", "--reason", "fixture", "--file", str(self.path)
        )
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)


if __name__ == "__main__":
    unittest.main()
