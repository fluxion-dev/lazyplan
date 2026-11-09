"""Legacy CLI aliases stay alive with one stderr deprecation notice."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from lazyplan.infrastructure.environment import parse_version
from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.presentation.cli.parser import package_version
from lazyplan.presentation.shared import registry
from lazyplan.presentation.shared.help import HELP_TEXT


class LegacyDeprecationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "legacy.db")
        self.env = {
            "LAZYPLAN_NO_SETUP": "1",
            "LAZYPLAN_NO_UPDATE_CHECK": "1",
        }
        self.saved = {key: os.environ.get(key) for key in self.env}
        os.environ.update(self.env)

    def tearDown(self) -> None:
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str]:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = lpui_main(["--db", self.db, *argv])
        return code, stderr.getvalue()

    def test_legacy_alias_runs_and_prints_one_notice(self) -> None:
        code, stderr = self._run(["add-plan", "--title", "Legacy", "--what", "What"])
        self.assertEqual(code, 0)
        self.assertIn("deprecated", stderr)
        self.assertIn("lpui plan add", stderr)
        self.assertIn("0.37.0", stderr)

    def test_porcelain_and_json_stay_machine_clean(self) -> None:
        for flags in (["--porcelain"], ["--json"]):
            with self.subTest(flags=flags):
                code, stderr = self._run(
                    [*flags, "add-plan", "--title", "Machine", "--what", "What"]
                )
                self.assertEqual(code, 0)
                self.assertNotIn("deprecated", stderr)

    def test_canonical_noun_form_is_silent(self) -> None:
        code, stderr = self._run(["plan", "add", "--title", "Canonical", "--what", "What"])
        self.assertEqual(code, 0)
        self.assertNotIn("deprecated", stderr)

    def test_every_deprecation_names_a_removal_release(self) -> None:
        rows = registry.deprecations()
        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(name=row.name):
                self.assertEqual(row.removal, registry.DEPRECATION_RELEASE)
                self.assertTrue(row.replacement)

    def test_removal_guard_fails_once_the_window_closes(self) -> None:
        current = parse_version(package_version())
        removal = parse_version(registry.DEPRECATION_RELEASE)
        if current >= removal:
            self.assertEqual(
                registry.deprecations(),
                (),
                f"remove the deprecated aliases before {registry.DEPRECATION_RELEASE}",
            )

    def test_help_shows_the_moved_keys(self) -> None:
        self.assertIn("DEPRECATED", HELP_TEXT)
        self.assertIn("removed in 0.37.0", HELP_TEXT)
        self.assertIn("ctrl+r", HELP_TEXT)

    def test_moved_actions_stay_reachable_from_the_palette(self) -> None:
        from lazyplan.presentation.shared.palette import by_id

        for command_id in ("add-question", "resolve-question", "reopen-question"):
            with self.subTest(command=command_id):
                self.assertIsNotNone(by_id(command_id))


if __name__ == "__main__":
    unittest.main()
