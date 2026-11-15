"""Setup wizard rendering ends every line with a newline."""

import io
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import host_models, profiles, skills
from lazyplan.presentation.setup import ui as setup_ui


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
        self.assertIn("4/4 Review", lines[0])
        self.assertTrue(any("database" in line for line in lines))
        self.assertTrue(any("state" in line for line in lines))
        self.assertTrue(any("plugins" in line for line in lines))

    def test_review_names_each_plugin(self):
        text = self._text(
            lambda out: setup_ui.render_review(
                out,
                self.home / "db.sqlite",
                self.home / "templates",
                [],
                self.home / "setup.json",
                None,
                False,
                [("OpenCode", self.home / "plugins" / "lazyplan.js")],
            )
        )
        lines = self._lines(text)
        plugin_line = next(line for line in lines if "plugins" in line)
        self.assertIn("OpenCode", plugin_line)
        self.assertIn("lazyplan.js", plugin_line)

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

    def test_model_review_lists_tiers_roles_and_sources(self):
        catalogs = {
            "opencode": host_models.HostCatalog(
                "opencode",
                "OpenCode",
                ("provider/tiny", "provider/big"),
                {"fast": "provider/tiny", "standard": "provider/big", "deep": "provider/big"},
                "opencode models",
            ),
            "claude": host_models.HostCatalog(
                "claude",
                "Claude Code",
                ("haiku", "sonnet", "opus"),
                {"fast": "haiku", "standard": "sonnet", "deep": "opus"},
                "Claude Code aliases",
            ),
        }
        text = self._text(
            lambda out: setup_ui.render_models(
                out,
                ["opencode", "claude"],
                profiles.defaults(),
                profiles.default_tiers(),
                catalogs,
                False,
            )
        )
        lines = self._lines(text)
        self.assertIn("3/4 Model targets", lines[0])
        self.assertTrue(any("fast" in line and "provider/tiny" in line for line in lines))
        self.assertTrue(any("scout" in line and "haiku" in line for line in lines))
        self.assertTrue(any("sources:" in line and "opencode models" in line for line in lines))
        self.assertTrue(any("enter accept" in line for line in lines))
        self.assertNotIn("\x1b", text)

    def test_model_review_marks_a_catalog_warning(self):
        catalog = host_models.HostCatalog(
            "opencode",
            "OpenCode",
            warning="OpenCode is not detected",
        )
        text = self._text(
            lambda out: setup_ui.render_models(
                out,
                ["opencode"],
                profiles.defaults(),
                profiles.default_tiers(),
                {"opencode": catalog},
                False,
            )
        )
        self.assertIn("OpenCode is not detected", text)
        self.assertIn("inherit", text)


if __name__ == "__main__":
    unittest.main()
