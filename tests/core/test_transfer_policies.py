"""Pure transfer rules: export shape, sync diffs, redaction, and stamps."""

from __future__ import annotations

import unittest

from lazyplan.core.policies.transfer import (
    differences,
    is_export,
    issue_stamp,
    safe_payload,
    summary,
)


class TestExport(unittest.TestCase):
    def test_version_check(self) -> None:
        self.assertTrue(is_export({"lazyplan": 1, "plans": []}))
        self.assertFalse(is_export({"lazyplan": 2}))
        self.assertFalse(is_export(None))

    def test_summary_counts(self) -> None:
        entry = {
            "plan": {"name": "P", "goal": "why", "description": "what", "status": "todo"},
            "criteria": [{"text": "a"}],
            "milestones": [{"criteria": [{"text": "b"}], "tasks": [{"criteria": [{"text": "c"}]}]}],
        }
        self.assertEqual(summary(entry)["tasks"], 1)
        self.assertEqual(summary(entry)["criteria"], 3)

    def test_differences(self) -> None:
        left = {"plan": {"name": "A"}}
        right = {"plan": {"name": "B"}}
        self.assertEqual(differences(left, right), ["name"])


class TestRedaction(unittest.TestCase):
    def test_payload_is_dropped_recursively(self) -> None:
        data = {"keep": 1, "payload": "secret", "items": [{"payload": "x", "text": "y"}]}
        self.assertEqual(safe_payload(data), {"keep": 1, "items": [{"text": "y"}]})


class TestStamps(unittest.TestCase):
    def test_iso_and_missing(self) -> None:
        self.assertGreater(issue_stamp("2026-01-01T00:00:00Z"), 0)
        self.assertEqual(issue_stamp(""), 0.0)
        self.assertEqual(issue_stamp("not a date"), 0.0)


if __name__ == "__main__":
    unittest.main()
