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
from lazyplan.models import Project, Task, UserStory
from lazyplan.store import Store


class TestDesignSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_label_grammar(self):
        p = Project(id=1, name="N", priority="p1")
        self.assertEqual(design.project_label(p), "⬜ P#1 !p1 N")
        s = UserStory(id=2, project_id=1, title="S", priority="p0")
        self.assertEqual(design.story_label(s), "⬜ S#2 !p0 S")
        t = Task(id=3, story_id=2, title="T")
        self.assertEqual(design.task_label(t), "⬜ T#3 T")
        self.assertEqual(design.priority_tag(""), "")

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
        p = Project(id=1, name="N", priority="p1")
        self.assertIn("\x1b[33m⬜\x1b[0m P#1", design.project_label(p, dot="ansi"))
        s = UserStory(id=2, project_id=1, title="S")
        self.assertTrue(design.story_label(s, dot="ansi").startswith("\x1b[33m⬜\x1b[0m S#2"))
        t = Task(id=3, story_id=2, title="T")
        self.assertTrue(design.task_label(t, dot="ansi").startswith("\x1b[33m⬜\x1b[0m T#3"))
        self.assertNotIn("\x1b[", design.project_label(p))

    def test_rich_rows_for_tui(self):
        s = UserStory(id=2, project_id=1, title="S")
        self.assertTrue(design.story_row(s).startswith("[yellow]⬜[/]"))
        self.assertIn("S#2 S", design.story_row(s))
        self.assertEqual(design.story_row(s).count("⬜"), 1)
        t = Task(id=3, story_id=2, title="T")
        self.assertTrue(design.task_row(t).startswith("[yellow]⬜[/]"))
        self.assertEqual(design.task_row(t).count("⬜"), 1)
        p = Project(id=1, name="N")
        self.assertEqual(design.project_row(p).count("⬜"), 1)

    def test_criteria_progress_in_labels(self):
        p = self.store.add_project("P")
        self.store.add_criteria("project", p.id, "done-thing", actor="t")
        c2 = self.store.add_criteria("project", p.id, "open-thing", actor="t")
        self.assertIn("[0/2✓]", design.project_label(p, self.store))
        self.store.set_criteria(c2.id, True, actor="t")
        self.assertIn("[1/2✓]", design.project_label(p, self.store))

    def test_project_row_pill_and_escaped_title(self):
        p = Project(id=1, name="Ray [old]", priority="p1")
        self.assertEqual(design.project_row(p), "[yellow]⬜[/] [reverse] P1 [/] !p1 Ray \\[old]")
        self.assertNotIn("TODO", design.project_row(p))

    def test_cli_uses_design_labels(self):
        p = self.store.add_project("P", priority="p1")
        s = self.store.add_story(p.id, "S", priority="p0")
        t = self.store.add_task(s.id, "T")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "list"]), 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], design.project_label(p, self.store))
        self.assertEqual(lines[1], "  " + design.story_label(s, self.store))
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
        for const in (design.EMPTY_NO_PROJECTS, design.EMPTY_FEED):
            self.assertTrue(isinstance(const, str) and len(const) > 0)


if __name__ == "__main__":
    unittest.main()
