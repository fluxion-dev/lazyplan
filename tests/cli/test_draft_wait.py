"""`lpui draft wait`: wake on saved feedback, stop on promotion, give up on timeout."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services import drafts
from lazyplan.store import Store
from tests.support.paths import ROOT

from .test_drafts import document

WAKE_BUDGET_SECONDS = 2.0


class DraftWaitCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        self.draft = drafts.create(self.store, document())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_a_running_wait_wakes_on_an_annotation_from_another_process(self) -> None:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "LAZYPLAN_HOOKS": "off"}
        waiter = subprocess.Popen(
            [sys.executable, "-m", "lazyplan", "--db", self.db, "--json", "draft", "wait"]
            + ["--id", str(self.draft.id), "--timeout", "30"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.addCleanup(waiter.kill)
        time.sleep(1.5)
        self.assertIsNone(waiter.poll(), "wait exited before any feedback was saved")
        saved_at = time.monotonic()
        drafts.annotate(self.store, self.draft.id, "plan:why", "change", "Sharpen")
        out, err = waiter.communicate(timeout=10)
        elapsed = time.monotonic() - saved_at
        self.assertEqual(waiter.returncode, 0, err)
        self.assertLess(elapsed, WAKE_BUDGET_SECONDS)
        self.assertEqual([row["body"] for row in json.loads(out)], ["Sharpen"])

    def test_promoted_draft_exits_3(self) -> None:
        drafts.promote(self.store, self.draft.id)
        code, out, _err = self._run("--porcelain", "draft", "wait", "--id", str(self.draft.id))
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("draft\t"))

    def test_timeout_exits_4(self) -> None:
        code, _out, err = self._run("draft", "wait", "--id", str(self.draft.id), "--timeout", "0.2")
        self.assertEqual(code, 4)
        self.assertIn("no open feedback on D1", err)

    def test_missing_draft_exits_1(self) -> None:
        code, _out, err = self._run("draft", "wait", "--id", "99", "--timeout", "0.2")
        self.assertEqual(code, 1)
        self.assertIn("draft #99 not found", err)


if __name__ == "__main__":
    unittest.main()
