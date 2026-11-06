"""Plan document validation: stable keys, structure, templates, and criteria."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lazyplan.services.plan_document import (
    PlanDocumentError,
    counts,
    load_document,
    preview,
    validate_document,
)
from lazyplan.store import Store


def document() -> dict:
    return {
        "plan": {
            "key": "demo-plan",
            "title": "Demo plan",
            "why": "Why this matters.",
            "what": "## Scope\n\n- One thing.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "build",
                "title": "Build it",
                "desc": "As a user, I want the change.",
                "criteria": ["Built."],
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement it",
                        "desc": "Approach: do the work.\n\nCommit: one slice.\n\nVerify: tests pass.",
                        "criteria": ["Tests pass."],
                    }
                ],
            }
        ],
    }


class PlanDocumentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_document_resolves_and_counts(self):
        parsed = validate_document(self.store, document())
        self.assertEqual(parsed.key, "demo-plan")
        self.assertEqual(parsed.title, "Demo plan")
        self.assertEqual(parsed.milestones[0].tasks[0].title, "Implement it")
        self.assertEqual(counts(parsed), {"milestones": 1, "tasks": 1, "criteria": 3})

    def test_preview_is_a_compact_tree(self):
        parsed = validate_document(self.store, document())
        tree = preview(parsed)
        self.assertEqual(tree["plan"]["key"], "demo-plan")
        self.assertEqual(tree["milestones"][0]["tasks"][0]["key"], "impl")

    def test_unknown_top_level_field(self):
        raw = document()
        raw["extra"] = True
        with self.assertRaisesRegex(PlanDocumentError, "unknown field"):
            validate_document(self.store, raw)

    def test_unknown_plan_field(self):
        raw = document()
        raw["plan"]["owner"] = "someone"
        with self.assertRaisesRegex(PlanDocumentError, "unknown field"):
            validate_document(self.store, raw)

    def test_missing_plan(self):
        raw = document()
        del raw["plan"]
        with self.assertRaisesRegex(PlanDocumentError, "plan is required"):
            validate_document(self.store, raw)

    def test_missing_key(self):
        raw = document()
        del raw["plan"]["key"]
        with self.assertRaisesRegex(PlanDocumentError, "key must be a string"):
            validate_document(self.store, raw)

    def test_duplicate_milestone_key(self):
        raw = document()
        raw["milestones"].append(dict(raw["milestones"][0]))
        with self.assertRaisesRegex(PlanDocumentError, "duplicate milestone key"):
            validate_document(self.store, raw)

    def test_duplicate_task_key_across_milestones(self):
        raw = document()
        raw["milestones"].append(
            {
                "key": "second",
                "title": "Second",
                "desc": "Another milestone.",
                "tasks": [dict(raw["milestones"][0]["tasks"][0])],
            }
        )
        with self.assertRaisesRegex(PlanDocumentError, "duplicate task key"):
            validate_document(self.store, raw)

    def test_duplicate_criterion(self):
        raw = document()
        raw["plan"]["criteria"] = ["Works.", "Works."]
        with self.assertRaisesRegex(PlanDocumentError, "duplicate criterion"):
            validate_document(self.store, raw)

    def test_placeholder_marker(self):
        raw = document()
        raw["plan"]["title"] = "TODO name"
        with self.assertRaisesRegex(PlanDocumentError, "placeholder"):
            validate_document(self.store, raw)

    def test_unreadable_long_why(self):
        raw = document()
        raw["plan"]["why"] = "x" * 301
        with self.assertRaisesRegex(PlanDocumentError, "readable 'why'"):
            validate_document(self.store, raw)

    def test_load_document_round_trips(self):
        path = Path(self.tmp.name) / "plan.json"
        path.write_text(json.dumps(document()), encoding="utf-8")
        self.assertEqual(load_document(path)["plan"]["key"], "demo-plan")

    def test_load_document_rejects_invalid_json(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_text("{nope", encoding="utf-8")
        with self.assertRaisesRegex(PlanDocumentError, "invalid JSON"):
            load_document(path)

    def test_load_document_rejects_non_object(self):
        path = Path(self.tmp.name) / "list.json"
        path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(PlanDocumentError, "expected a JSON object"):
            load_document(path)

    def test_missing_file(self):
        with self.assertRaisesRegex(PlanDocumentError, "cannot read"):
            load_document(Path(self.tmp.name) / "missing.json")


if __name__ == "__main__":
    unittest.main()
