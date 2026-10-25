"""Setup wizard rendering ends every line with a newline."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import setup_ui, skills  # noqa: E402


class RenderCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _text(self, draw) -> str:
        out = io.StringIO()
        draw(out)
        return out.getvalue()

    def _lines(self, text: str) -> list[str]:
        return text.splitlines()

    def test_banner_writes_separate_lines(self):
        text = self._text(lambda out: setup_ui.banner(out, False, "0.0.0"))
        lines = self._lines(text)
        self.assertGreaterEqual(len(lines), 3)
        self.assertIn("lazyplan setup", lines[0])
        self.assertNotIn("\x1b", text)

    def test_color_only_when_requested(self):
        plain = self._text(lambda out: setup_ui.banner(out, False, "0.0.0"))
        colored = self._text(lambda out: setup_ui.banner(out, True, "0.0.0"))
        self.assertNotIn("\x1b", plain)
        self.assertIn("\x1b", colored)

    def test_placement_choices_are_one_per_line(self):
        text = self._text(
            lambda out: setup_ui.render_placement(out, None, self.home, "home", False)
        )
        lines = self._lines(text)
        self.assertEqual(len(lines), 3)  # choice + two wrapped note lines
        self.assertIn("Home", lines[0])
        self.assertIn(str(self.home / ".lazyplan/lazyplan.db"), lines[0])

    def test_review_rows_are_one_per_line(self):
        text = self._text(
            lambda out: setup_ui.render_review(
                out,
                self.home / "db.sqlite",
                self.home / "templates",
                [self.home / "SKILL.md"],
                self.home / "setup.json",
                None,
                False,
            )
        )
        lines = self._lines(text)
        self.assertIn("3/3 Review", lines[0])
        self.assertTrue(any("database" in line for line in lines))
        self.assertTrue(any("state" in line for line in lines))

    def test_success_and_note_are_line_broken(self):
        text = self._text(
            lambda out: (
                setup_ui.success(out, self.home / "db", [self.home / "skill"], [], False),
                setup_ui.note(out, "heads up", False),
            )
        )
        lines = self._lines(text)
        self.assertIn("Setup complete", lines[0])
        self.assertIn("heads up", lines[-1])

    def test_host_rows_are_one_per_line(self):
        hosts = skills.detect_agents(self.home)
        text = self._text(lambda out: setup_ui.render_agents(out, hosts, [], False))
        self.assertEqual(len(self._lines(text)), len(hosts))


if __name__ == "__main__":
    unittest.main()
