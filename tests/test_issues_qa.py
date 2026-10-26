"""Issue import QA: GitHub live path, dedupe, source refs, and secret hygiene."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from home_sandbox import sandbox_home  # noqa: E402

from lazyplan import services  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402

GITHUB = [
    {
        "number": 7,
        "title": "Fix login",
        "body": "details",
        "state": "open",
        "html_url": "https://github.com/o/r/issues/7",
        "updated_at": "2026-01-02T03:04:05Z",
    },
    {"number": 8, "title": "PR", "pull_request": {"url": "x"}},
]


class TestIssueQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "qa.db")
        Store(self.db).add_plan("P", actor="fixture")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "qa", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_github_live_import_is_explicit_and_dedupes(self):
        with mock.patch(
            "lazyplan.cli.GitHubClient.issues", return_value=SimpleNamespace(data=GITHUB)
        ) as fetched:
            code, out, err = self._run(
                "--json", "issue", "import", "--provider", "github", "--repo", "o/r"
            )
            self.assertEqual(code, 0, err)
            report = json.loads(out)
            self.assertEqual(len(report["created"]), 1)
            self.assertEqual(fetched.call_count, 1)
            code, out, err = self._run(
                "--json", "issue", "import", "--provider", "github", "--repo", "o/r"
            )
            self.assertEqual(json.loads(out)["created"], [])
        store = Store(self.db)
        import_plan = next(plan for plan in store.list_plans() if plan.name == "Fix login")
        refs = store.list_issue_links("plan", import_plan.id)
        self.assertEqual(refs[0]["url"], "https://github.com/o/r/issues/7")
        code, out, err = self._run("plan", "show", "--id", str(import_plan.id))
        self.assertIn("source: github #7", out)
        data = services.export_all(store)
        self.assertNotIn("token", json.dumps(data).lower())

    def test_bad_github_repo_exits_two_without_network(self):
        code, out, err = self._run("issue", "import", "--provider", "github")
        self.assertEqual(code, 2)
        self.assertIn("--repo", err)


if __name__ == "__main__":
    unittest.main()
