"""Legacy CLI aliases are gone; the guard has nothing left to remove."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from lazyplan.presentation.cli.main import main as lpui_main
from lazyplan.presentation.shared import registry


class LegacyRemovalTest(unittest.TestCase):
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

    def test_flat_verbs_are_rejected(self) -> None:
        for verb in ("add-plan", "add-task", "update", "status", "delete", "show"):
            with self.subTest(verb=verb):
                with self.assertRaises(SystemExit) as caught:
                    self._run([verb, "--help"])
                self.assertEqual(caught.exception.code, 2)

    def test_canonical_noun_form_still_works(self) -> None:
        code, stderr = self._run(["plan", "add", "--title", "Canonical", "--what", "What"])
        self.assertEqual(code, 0)
        self.assertNotIn("deprecated", stderr)

    def test_no_deprecations_remain(self) -> None:
        self.assertEqual(registry.deprecations(), ())
        self.assertEqual(registry.legacy_notice("add-plan"), None)


if __name__ == "__main__":
    unittest.main()
