"""The repeat runner discovers, shuffles deterministically, and validates quarantine."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tests.support.paths import ROOT


def _load():
    spec = importlib.util.spec_from_file_location("repeat_tests", ROOT / "tools/repeat-tests.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RepeatRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = _load()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "quarantine.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_all_tests_are_flattened(self) -> None:
        ids = [test.id() for test in self.tool.all_tests()]
        self.assertTrue(any(test.startswith("tests.architecture.") for test in ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_tui_excludes_presentation(self) -> None:
        ids = [test.id() for test in self.tool.all_tests(no_tui=True)]
        self.assertFalse(any(test.startswith("tests.presentation") for test in ids))
        self.assertFalse(any(test == "tests.setup.test_setup_pty" for test in ids))

    def test_a_seed_is_reproducible(self) -> None:
        names = ["a", "b", "c", "d"]
        self.assertEqual(
            self.tool.shuffled(names, 7, 0),
            self.tool.shuffled(names, 7, 0),
        )
        self.assertNotEqual(self.tool.shuffled(names, 7, 0), self.tool.shuffled(names, 7, 1))

    def test_an_empty_quarantine_is_valid(self) -> None:
        self.path.write_text('{"tests": []}', encoding="utf-8")
        self.assertEqual(self.tool.load_quarantine(self.path), [])

    def test_a_quarantine_entry_needs_a_task_reason_and_expiry(self) -> None:
        self.path.write_text(
            json.dumps({"tests": [{"id": "tests.x.test_y", "task": 24}]}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            self.tool.load_quarantine(self.path)

    def test_an_expired_quarantine_fails(self) -> None:
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        self.path.write_text(
            json.dumps(
                {
                    "tests": [
                        {
                            "id": "tests.x.test_y",
                            "task": 24,
                            "reason": "known race",
                            "expires": yesterday,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            self.tool.load_quarantine(self.path)

    def test_a_future_quarantine_is_valid(self) -> None:
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        self.path.write_text(
            json.dumps(
                {
                    "tests": [
                        {
                            "id": "tests.x.test_y",
                            "task": 24,
                            "reason": "known race",
                            "expires": tomorrow,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(len(self.tool.load_quarantine(self.path)), 1)


if __name__ == "__main__":
    unittest.main()
