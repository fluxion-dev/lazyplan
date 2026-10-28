"""Issue import: provider parsing, dedupe, placement, and dry-run."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from lazyplan import issues, services
from lazyplan.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home

GITHUB = [
    {
        "number": 7,
        "title": "Fix login",
        "body": "details",
        "state": "open",
        "html_url": "https://github.com/o/r/issues/7",
        "updated_at": "2026-01-02T03:04:05Z",
    },
    {
        "number": 8,
        "title": "A PR",
        "pull_request": {"url": "x"},
    },
]

LINEAR = {
    "data": {
        "issues": {
            "nodes": [
                {
                    "identifier": "ENG-4",
                    "title": "Linear thing",
                    "description": "body",
                    "url": "https://linear.app/o/issue/ENG-4",
                    "state": {"name": "Todo"},
                    "updatedAt": "2026-01-03T00:00:00Z",
                }
            ]
        }
    }
}


class TestIssueImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "issues.db"))
        plan = self.store.add_plan("P", actor="fixture")
        self.milestone = self.store.add_milestone(plan.id, "M", actor="fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parsers_normalize_and_skip_prs(self):
        github = issues.parse_github(GITHUB)
        self.assertEqual(len(github), 1)
        self.assertEqual(github[0].provider, "github")
        self.assertEqual(github[0].external_id, "7")
        self.assertGreater(github[0].updated_at, 0)
        linear = issues.parse_linear(LINEAR)
        self.assertEqual(linear[0].external_id, "ENG-4")
        self.assertEqual(linear[0].state, "Todo")

    def test_import_creates_and_dedupes(self):
        report = issues.import_issues(self.store, issues.parse_github(GITHUB), actor="fixture")
        self.assertEqual(len(report["created"]), 1)
        self.assertEqual(self.store.get_plan(2).name, "Fix login")
        link = self.store.get_issue_link("github", "7")
        assert link is not None
        self.assertEqual(link["row_kind"], "plan")
        second = issues.import_issues(self.store, issues.parse_github(GITHUB), actor="fixture")
        self.assertEqual(second["created"], [])
        self.assertEqual(len(second["updated"]), 1)
        self.assertEqual(len(self.store.list_plans()), 2)  # P plus imported

    def test_task_placement(self):
        report = issues.import_issues(
            self.store,
            issues.parse_linear(LINEAR),
            actor="fixture",
            as_kind="task",
            milestone=self.milestone.id,
        )
        self.assertEqual(report["created"][0]["row_kind"], "task")
        self.assertEqual(self.store.list_tasks(self.milestone.id)[0].title, "Linear thing")

    def test_dry_run_writes_nothing(self):
        report = issues.import_issues(
            self.store, issues.parse_github(GITHUB), actor="fixture", dry_run=True
        )
        self.assertEqual(len(report["created"]), 1)
        self.assertEqual(len(self.store.list_plans()), 1)
        self.assertIsNone(self.store.get_issue_link("github", "7"))

    def test_task_without_milestone_is_rejected(self):
        with self.assertRaises(ValueError):
            issues.import_issues(self.store, issues.parse_github(GITHUB), as_kind="task")


class TestIssueCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "cli.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        store.add_milestone(plan.id, "M", actor="fixture")
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

    def test_linear_file_import_and_source_refs(self):
        path = os.path.join(self.tmp.name, "linear.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(LINEAR, fh)
        code, out, err = self._run(
            "--json", "issue", "import", "--provider", "linear", "--file", path
        )
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual(len(report["created"]), 1)
        link = Store(self.db).get_issue_link("linear", "ENG-4")
        assert link is not None
        code, out, err = self._run("plan", "show", "--id", "2")
        self.assertIn("source: linear #ENG-4", out)
        code, out, err = self._run("--porcelain", "plan", "show", "--id", "2")
        self.assertIn("issue\tENG-4", out)

    def test_dry_run_and_bad_input(self):
        path = os.path.join(self.tmp.name, "linear.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(LINEAR, fh)
        code, out, err = self._run(
            "issue", "import", "--provider", "linear", "--file", path, "--dry-run"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("dry-run", out)
        self.assertIsNone(Store(self.db).get_issue_link("linear", "ENG-4"))
        code, out, err = self._run("issue", "import", "--provider", "linear")
        self.assertEqual(code, 2)
        self.assertIn("--file", err)
        code, out, err = self._run(
            "issue", "import", "--provider", "linear", "--file", path, "--as", "task"
        )
        self.assertEqual(code, 2)

    def test_export_import_preserves_issue_refs(self):
        store = Store(self.db)
        issues.import_issues(store, issues.parse_linear(LINEAR), actor="fixture")
        data = services.export_all(store)
        refs = next(entry["issues"] for entry in data["plans"] if entry.get("issues"))
        self.assertEqual(refs[0]["external_id"], "ENG-4")
        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["issues"], 1)
        imported = next(plan for plan in other.list_plans() if plan.name == "Linear thing")
        self.assertEqual(other.list_issue_links("plan", imported.id)[0]["external_id"], "ENG-4")


if __name__ == "__main__":
    unittest.main()
