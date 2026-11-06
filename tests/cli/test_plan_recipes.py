"""Packaged plan recipes: storeless output and dry-run validity."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from tests.support.home import sandbox_home


class PlanRecipeCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_cwd = os.getcwd()
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        if self.old_nosetup is None:
            os.environ.pop(setup.NO_SETUP_ENV, None)
        else:
            os.environ[setup.NO_SETUP_ENV] = self.old_nosetup
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(list(argv))
        return code, out.getvalue()

    def test_recipe_is_storeless(self):
        code, out = self._run("--json", "plan", "recipe", "feature")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["plan"]["key"], "feature")
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_each_recipe_dry_runs_with_qa_docs_and_refactor(self):
        for name in ("feature", "bugfix", "refactor"):
            with self.subTest(recipe=name):
                code, out = self._run("--json", "plan", "recipe", name)
                self.assertEqual(code, 0)
                document = json.loads(out)
                path = Path(self.tmp.name) / f"{name}.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                db = Path(self.tmp.name) / f"{name}.db"
                code, out = self._run(
                    "--db",
                    str(db),
                    "--json",
                    "plan",
                    "apply",
                    "--file",
                    str(path),
                    "--dry-run",
                )
                self.assertEqual(code, 0)
                payload = json.loads(out)
                self.assertTrue(payload["dry_run"])
                self.assertEqual(payload["counts"]["milestones"], 1)
                tasks = payload["milestones"][0]["tasks"]
                titles = " ".join(task["title"].lower() for task in tasks)
                for word in ("test", "doc", "refactor"):
                    self.assertIn(word, titles)
                self.assertNotRegex(json.dumps(document), r"\b(TODO|TBD|FIXME)\b")

    def test_unknown_recipe_is_rejected_by_the_parser(self):
        with self.assertRaises(SystemExit):
            lpui_main(["plan", "recipe", "nope"])


if __name__ == "__main__":
    unittest.main()
