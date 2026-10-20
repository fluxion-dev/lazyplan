"""Internal-consistency tests: CLI and TUI must render from design helpers."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import design
from lazyplan.cli import main as lpui_main
from lazyplan.models import Milestone, Plan, Task
from lazyplan.store import Store


class TestDesignSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_label_grammar(self):
        p = Plan(id=1, name="N", priority="p1")
        self.assertEqual(design.plan_label(p), "⬜ P#1 N")
        s = Milestone(id=2, plan_id=1, title="S", priority="p0")
        self.assertEqual(design.milestone_label(s), "⬜ M#2 S")
        t = Task(id=3, milestone_id=2, title="T")
        self.assertEqual(design.task_label(t), "⬜ T#3 T")
        # priority stays on the model but never renders in headers
        self.assertNotIn("!p1", design.plan_label(p))
        self.assertNotIn("!p0", design.milestone_label(s))

    def test_status_word_forms(self):
        self.assertEqual(design.status_word("todo"), "⬜")
        self.assertEqual(design.status_word("doing", "ansi"), "\x1b[34m🔵\x1b[0m")
        self.assertEqual(design.status_word("done", "ansi"), "\x1b[32m✅\x1b[0m")
        self.assertEqual(design.status_word("todo", "ansi"), "\x1b[33m⬜\x1b[0m")
        self.assertEqual(design.status_word("doing", "rich"), "[blue]🔵[/]")
        self.assertEqual(design.status_word("done", "rich"), "[green]✅[/]")
        self.assertEqual(design.status_word("todo", "rich"), "[yellow]⬜[/]")
        with self.assertRaises(ValueError):
            design.status_word("todo", "neon")

    def test_ansi_labels_colorize_the_word(self):
        p = Plan(id=1, name="N", priority="p1")
        self.assertIn("\x1b[33m⬜\x1b[0m P#1", design.plan_label(p, dot="ansi"))
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertTrue(design.milestone_label(s, dot="ansi").startswith("\x1b[33m⬜\x1b[0m M#2"))
        t = Task(id=3, milestone_id=2, title="T")
        self.assertTrue(design.task_label(t, dot="ansi").startswith("\x1b[33m⬜\x1b[0m T#3"))
        self.assertNotIn("\x1b[", design.plan_label(p))

    def test_rich_rows_for_tui(self):
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertTrue(design.milestone_row(s).startswith("[yellow]⬜[/]"))
        self.assertIn("M#2 S", design.milestone_row(s))
        self.assertEqual(design.milestone_row(s).count("⬜"), 1)
        t = Task(id=3, milestone_id=2, title="T")
        self.assertTrue(design.task_row(t).startswith("[yellow]⬜[/]"))
        self.assertEqual(design.task_row(t).count("⬜"), 1)
        p = Plan(id=1, name="N")
        self.assertEqual(design.plan_row(p).count("⬜"), 1)

    def test_no_criteria_progress_in_labels(self):
        p = self.store.add_plan("P")
        self.store.add_criteria("plan", p.id, "done-thing", actor="t")
        c2 = self.store.add_criteria("plan", p.id, "open-thing", actor="t")
        self.assertEqual(design.plan_label(p, self.store), "⬜ P#1 P")
        self.store.set_criteria(c2.id, True, actor="t")
        label = design.plan_label(p, self.store)
        self.assertEqual(label, "⬜ P#1 P")
        self.assertNotRegex(label, r"\[\d+/\d+✓\]")

    def test_plan_row_pill_and_escaped_title(self):
        p = Plan(id=1, name="Ray [old]", priority="p1")
        self.assertEqual(design.plan_row(p), "[yellow]⬜[/] [reverse] P1 [/] Ray \\[old]")
        self.assertNotIn("TODO", design.plan_row(p))

    def test_cli_uses_design_labels(self):
        p = self.store.add_plan("P", priority="p1")
        s = self.store.add_milestone(p.id, "S", priority="p0")
        t = self.store.add_task(s.id, "T")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "list"]), 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], design.plan_label(p, self.store))
        self.assertEqual(lines[1], "  " + design.milestone_label(s, self.store))
        self.assertEqual(lines[2], "    " + design.task_label(t, self.store))

    def test_help_single_source(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "help"]), 0)
        self.assertEqual(buf.getvalue().strip(), design.HELP_TEXT.strip())
        try:
            from lazyplan.screens import HelpScreen  # needs textual installed
        except ImportError:
            HelpScreen = None
        if HelpScreen is not None:
            self.assertEqual(HelpScreen.HELP.strip(), design.HELP_TEXT.strip())
        else:
            import pathlib

            src = (
                pathlib.Path(__file__).parent.parent.joinpath("src/lazyplan/screens.py").read_text()
            )
            self.assertIn("HELP = HELP_TEXT", src)
            self.assertIn("HELP_TEXT", src.split("from .design import")[1].split(")")[0])

    def test_message_helpers(self):
        self.assertEqual(design.msg_not_found("task", 7), "task #7 not found")
        self.assertTrue(design.msg_error(ValueError("x")).startswith("error:"))
        for const in (design.EMPTY_NO_PLANS, design.EMPTY_FEED):
            self.assertTrue(isinstance(const, str) and len(const) > 0)

    def test_commits_chip(self):
        self.assertEqual(design.commits_chip(None), "")
        self.assertEqual(design.commits_chip([]), "")
        sha = "a" * 40
        self.assertEqual(design.commits_chip([sha]), "[reverse] aaaaaaaaaaaa [/]")
        self.assertEqual(
            design.commits_chip([sha, "b" * 40]),
            "[reverse] aaaaaaaaaaaa [/] [reverse] bbbbbbbbbbbb [/]",
        )

    def test_rows_show_chips_only_when_linked(self):
        p = Plan(id=1, name="N", priority="p1")
        self.assertEqual(design.plan_row(p), design.plan_row(p, links=None))
        self.assertEqual(design.plan_row(p), design.plan_row(p, links=[]))
        self.assertIn("a" * 12, design.plan_row(p, links=["a" * 40]))

    def test_repo_project_name_prefers_remote(self):
        self.assertEqual(
            design.repo_project_name(
                {"repo_path": "/home/u/checkouts/api", "repo_remote": "git@github.com:org/api.git"}
            ),
            "api",
        )
        self.assertEqual(
            design.repo_project_name(
                {
                    "repo_path": "/home/u/checkouts/api",
                    "repo_remote": "https://github.com/org/web.git",
                }
            ),
            "web",
        )
        self.assertEqual(
            design.repo_project_name({"repo_path": "/home/u/checkouts/api", "repo_remote": ""}),
            "api",
        )
        self.assertEqual(design.repo_project_name({}), "")
        self.assertEqual(design.repo_project_name(None), "")

    def test_repos_chip(self):
        self.assertEqual(design.repos_chip(None), "")
        self.assertEqual(design.repos_chip([]), "")
        self.assertEqual(
            design.repos_chip([{"repo_path": "/x/api", "repo_remote": ""}]),
            "[reverse] api [/]",
        )

    def test_plan_label_shows_linked_project(self):
        p = self.store.add_plan("P")
        self.assertEqual(design.plan_label(p, self.store), "⬜ P#1 P")
        self.store.add_repo_link(
            "plan", p.id, "/home/u/checkouts/api", "git@github.com:org/api.git"
        )
        self.assertEqual(design.plan_label(p, self.store), "⬜ P#1 P [api]")

    def test_plan_row_shows_repo_pill(self):
        p = Plan(id=1, name="N", priority="p1")
        self.assertEqual(design.plan_row(p), design.plan_row(p, repos=None))
        self.assertEqual(design.plan_row(p), design.plan_row(p, repos=[]))
        row = design.plan_row(p, repos=[{"repo_path": "/x/api", "repo_remote": ""}])
        self.assertIn("[reverse] api [/]", row)
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertEqual(design.milestone_row(s), design.milestone_row(s, links=[]))
        self.assertIn("b" * 12, design.milestone_row(s, links=["b" * 40]))
        t = Task(id=3, milestone_id=2, title="T")
        self.assertEqual(design.task_row(t), design.task_row(t, links=None))
        self.assertIn("c" * 12, design.task_row(t, links=["c" * 40]))


if __name__ == "__main__":
    unittest.main()
