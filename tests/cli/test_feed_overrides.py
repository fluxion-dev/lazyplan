"""The feed override filter: only manual screen writes."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services.overrides import record_override
from lazyplan.store import Store
from tests.support.home import sandbox_home


class TestFeedOverrides(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "feed.db")
        self.store = Store(self.db)
        self.store.add_plan("Normal plan", actor="fixture")
        record_override(self.store, "approve", "plan #1", "reviewed")
        self.old = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self) -> None:
        if self.old is None:
            os.environ.pop("LAZYPLAN_NO_SETUP", None)
        else:
            os.environ["LAZYPLAN_NO_SETUP"] = self.old
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue()

    def test_only_override_events(self) -> None:
        code, out = self._run("--porcelain", "feed", "--overrides")
        self.assertEqual(code, 0)
        self.assertIn("override/approve", out)
        self.assertIn("reviewed", out)
        self.assertNotIn("plan/add", out)

    def test_default_feed_is_unchanged(self) -> None:
        code, out = self._run("--porcelain", "feed")
        self.assertEqual(code, 0)
        self.assertIn("plan/add", out)
        self.assertIn("override/approve", out)


if __name__ == "__main__":
    unittest.main()
