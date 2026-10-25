"""The porcelain contract: row grammar, escaping, and the global switch."""

from __future__ import annotations

import os
import sys
import unittest
from argparse import Namespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import porcelain  # noqa: E402
from lazyplan.cli_parser import build_parser  # noqa: E402


class TestRows(unittest.TestCase):
    def test_row_uses_the_documented_six_columns(self):
        self.assertEqual(
            porcelain.row("task", 12, "doing", "Design hero", "milestone:3", "-"),
            "task\t12\tdoing\tDesign hero\tmilestone:3\t-",
        )

    def test_missing_fields_use_a_dash(self):
        self.assertEqual(
            porcelain.row("plan", 1, "todo", "Website"), "plan\t1\ttodo\tWebsite\t-\t-"
        )

    def test_tabs_and_newlines_flatten_to_spaces(self):
        row = porcelain.row("task", 1, "todo", "Line one\tLine\ntwo\rthree", "milestone:1")
        self.assertEqual(row, "task\t1\ttodo\tLine one Line two three\tmilestone:1\t-")
        self.assertEqual(len(row.split("\t")), 6)

    def test_no_glyphs_or_ansi_are_emitted(self):
        row = porcelain.row("plan", 1, "doing", "Plan", "-", "1/2")
        for text in ("○", "◐", "●", "\x1b"):
            self.assertNotIn(text, row)


class TestSwitch(unittest.TestCase):
    def test_flag_enables(self):
        self.assertTrue(porcelain.enabled(Namespace(porcelain=True, json=False)))

    def test_json_wins_over_the_flag(self):
        self.assertFalse(porcelain.enabled(Namespace(porcelain=True, json=True)))

    def test_environment_truthy_values(self):
        for value in ("1", "true", "YES", " on "):
            with self.subTest(value=value):
                self.assertTrue(porcelain.env_enabled(value))

    def test_environment_falsey_values(self):
        for value in ("", "0", "false", "no", "off", "anything else"):
            with self.subTest(value=value):
                self.assertFalse(porcelain.env_enabled(value))

    def test_environment_reaches_enabled(self):
        with mock.patch.dict(os.environ, {porcelain.ENV: "1"}):
            self.assertTrue(porcelain.enabled(Namespace(json=False)))
        with mock.patch.dict(os.environ, {porcelain.ENV: "0"}):
            self.assertFalse(porcelain.enabled(Namespace(json=False)))


class TestParser(unittest.TestCase):
    def test_flag_works_before_and_after_the_verb(self):
        parser = build_parser()
        self.assertTrue(parser.parse_args(["--porcelain", "list"]).porcelain)
        self.assertTrue(parser.parse_args(["list", "--porcelain"]).porcelain)

    def test_flag_is_off_by_default(self):
        parser = build_parser()
        self.assertFalse(getattr(parser.parse_args(["list"]), "porcelain", False))

    def test_help_names_the_flag(self):
        text = build_parser().format_help()
        self.assertIn("--porcelain", text)
        self.assertIn("tab-separated", text)


if __name__ == "__main__":
    unittest.main()
