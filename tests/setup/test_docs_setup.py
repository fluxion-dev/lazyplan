"""Setup flags, environment, and files stay consistent across every surface."""

import argparse
import unittest

from lazyplan.cli.parser import build_parser
from lazyplan.docs_meta import ENVIRONMENT, FILES
from tests.support.paths import ROOT

USAGE = (ROOT / "docs/usage.md").read_text(encoding="utf-8")
SETUP_DOC = (ROOT / "docs/setup.md").read_text(encoding="utf-8")
MAN = (ROOT / "docs/lpui.1").read_text(encoding="utf-8").replace("\\-", "-").replace("\\.", ".")
README = (ROOT / "README.md").read_text(encoding="utf-8")


class DocsTruthCase(unittest.TestCase):
    def setUp(self):
        parser = build_parser()
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        self.commands = sub.choices

    def test_every_setup_flag_is_documented(self):
        for command in ("setup", "doctor", "upgrade"):
            for action in self.commands[command]._actions:
                if action.help == argparse.SUPPRESS or action.dest == "help":
                    continue
                for option in action.option_strings:
                    with self.subTest(command=command, option=option):
                        self.assertIn(option, USAGE)
                        self.assertIn(option, MAN)

    def test_documented_environment_matches_the_meta_table(self):
        for name, _text in ENVIRONMENT:
            first = name.split(",")[0].strip()
            with self.subTest(name=first):
                self.assertIn(first, USAGE)
                self.assertIn(first, MAN)

    def test_documented_files_match_the_meta_table(self):
        for name, _text in FILES:
            with self.subTest(name=name):
                self.assertIn(name.split(",")[0].strip(), MAN)

    def test_man_documents_porcelain(self):
        for needle in ("--porcelain", "LAZYPLAN_PORCELAIN", "--json still wins"):
            self.assertIn(needle, MAN)

    def test_removed_flags_stay_removed(self):
        for text in (README, USAGE, SETUP_DOC, MAN):
            self.assertNotIn("--team", text)

    def test_no_suppressed_flag_leaks(self):
        self.assertNotIn("SUPPRESS", MAN)

    def test_setup_walkthrough_names_every_placement(self):
        for word in ("home", "repo", "doctor", "upgrade", "uninstall"):
            self.assertIn(word, SETUP_DOC.lower())


if __name__ == "__main__":
    unittest.main()
