"""CLI Markdown export destinations: paths, overwrite rules, and errors."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.shared.render import render_plan_markdown
from lazyplan.services import export_plan
from lazyplan.store import Store
from tests.support.home import sandbox_home


class TestExportFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.db = str(self.root / "export.db")
        sandbox_home(self, self.root / "home")
        (self.root / "home").mkdir()
        self.old_cwd = os.getcwd()
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        store = Store(self.db)
        plan = store.add_plan("Website", "Marketing site", goal="Convert")
        store.add_criteria("plan", plan.id, "Loads fast")
        milestone = store.add_milestone(plan.id, "Homepage", "Hero work")
        store.add_task(milestone.id, "Design hero", "Hero section")
        self.plan_id = plan.id

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        if self.old_setup is None:
            os.environ.pop("LAZYPLAN_NO_SETUP", None)
        else:
            os.environ["LAZYPLAN_NO_SETUP"] = self.old_setup
        self.tmp.cleanup()

    def _run(self, *args: str) -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        os.chdir(self.work)
        try:
            with (
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
                mock.patch("sys.stdin", io.StringIO("")),
            ):
                code = lpui_main(["--db", self.db, *args])
        finally:
            os.chdir(self.old_cwd)
        return code, out.getvalue(), err.getvalue()

    def _markdown(self) -> str:
        entry = export_plan(Store(self.db), self.plan_id)
        assert entry is not None
        return render_plan_markdown(entry)

    def test_stdout_markdown_is_unchanged_without_a_file(self) -> None:
        code, out, _err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, self._markdown() + "\n")

    def test_file_receives_the_plan_markdown(self) -> None:
        target = self.root / "out" / "plan.md"
        code, out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(target),
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(target.read_text(encoding="utf-8"), self._markdown() + "\n")
        self.assertEqual(json.loads(out)["exported"], str(target.resolve()))

    def test_missing_parents_are_created(self) -> None:
        target = self.root / "a" / "b" / "c" / "plan.md"
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(target),
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(target.is_file())

    def test_tilde_is_expanded(self) -> None:
        target = Path(os.environ["HOME"]) / "notes" / "plan.md"
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            "~/notes/plan.md",
        )
        self.assertEqual(code, 0, err)
        self.assertTrue(target.is_file())

    def test_existing_directory_receives_the_default_name(self) -> None:
        target = self.root / "folder"
        target.mkdir()
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(target),
        )
        self.assertEqual(code, 0, err)
        self.assertTrue((target / f"plan-P{self.plan_id}.md").is_file())

    def test_existing_file_is_refused_without_force(self) -> None:
        target = self.work / "plan.md"
        target.write_text("old\n", encoding="utf-8")
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(target),
        )
        self.assertEqual(code, 2)
        self.assertIn("overwrite", err.lower())
        self.assertIn("plan.md", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    def test_force_replaces_an_existing_file(self) -> None:
        target = self.work / "plan.md"
        target.write_text("old\n", encoding="utf-8")
        code, out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(target),
            "--force",
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(target.read_text(encoding="utf-8"), self._markdown() + "\n")
        self.assertEqual(json.loads(out)["exported"], str(target.resolve()))

    def test_missing_plan_is_an_error(self) -> None:
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            "999",
            "--file",
            str(self.work / "plan.md"),
        )
        self.assertEqual(code, 1)
        self.assertIn("not found", err.lower())

    def test_unusable_parent_returns_two(self) -> None:
        blocker = self.work / "blocker"
        blocker.write_text("not a directory\n", encoding="utf-8")
        code, _out, err = self._run(
            "export",
            "--format",
            "markdown",
            "--plan",
            str(self.plan_id),
            "--file",
            str(blocker / "plan.md"),
        )
        self.assertEqual(code, 2)
        self.assertIn("could not export", err.lower())


if __name__ == "__main__":
    unittest.main()
