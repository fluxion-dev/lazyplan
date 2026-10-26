"""Internal-consistency tests: CLI, TUI, palette, and help share one design."""

import io
import os
import sys
import tempfile
import unicodedata
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import commands, design
from lazyplan.cli import main as lpui_main
from lazyplan.models import Milestone, Plan, Status, Task
from lazyplan.store import Store


class TestDesignSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_label_grammar(self):
        p = Plan(id=1, name="N")
        self.assertEqual(design.plan_label(p), "○ P1 N")
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertEqual(design.milestone_label(s), "○ M2 S")
        t = Task(id=3, milestone_id=2, title="T")
        self.assertEqual(design.task_label(t), "○ T3 T")
        # labels carry only status + id + title
        self.assertNotIn("p1", design.plan_label(p))
        self.assertNotIn("#", design.plan_label(p))

    def test_status_word_forms(self):
        self.assertEqual(design.status_word("todo"), "○")
        self.assertEqual(design.status_word("doing"), "◐")
        self.assertEqual(design.status_word("done"), "●")
        self.assertEqual(design.status_word("todo", "ansi"), "\x1b[90m○\x1b[0m")
        self.assertEqual(design.status_word("doing", "ansi"), "\x1b[33m◐\x1b[0m")
        self.assertEqual(design.status_word("done", "ansi"), "\x1b[32m●\x1b[0m")
        self.assertEqual(design.status_word("todo", "rich"), "[dim]○[/]")
        self.assertEqual(design.status_word("doing", "rich"), "[yellow]◐[/]")
        self.assertEqual(design.status_word("done", "rich"), "[green]●[/]")
        with self.assertRaises(ValueError):
            design.status_word("todo", "neon")

    def test_spinner_frames_and_prefix(self):
        self.assertEqual(design.SPINNER_FRAMES, ("◐", "◓", "◑", "◒"))
        self.assertEqual(design.SPINNER_INTERVAL, 0.16)
        for frame in design.SPINNER_FRAMES:
            self.assertEqual(len(frame), 1)
            self.assertNotIn(unicodedata.east_asian_width(frame), ("W", "F"))
        self.assertEqual(design.spinner_glyph(1), "◓")
        self.assertEqual(design.spinner_glyph(len(design.SPINNER_FRAMES)), "◐")
        self.assertEqual(design.status_prefix("doing"), "[yellow]◐[/]")
        self.assertEqual(design.status_prefix("doing", 1), "[yellow]◓[/]")
        self.assertEqual(design.status_prefix("doing", 7), "[yellow]◒[/]")
        self.assertEqual(design.status_prefix("todo", 2), "[dim]○[/]")
        self.assertEqual(design.status_prefix("done", 3), "[green]●[/]")
        self.assertEqual(design.status_word("doing", "rich"), "[yellow]◐[/]")

    def test_ansi_labels_colorize_the_word(self):
        p = Plan(id=1, name="N")
        self.assertIn("\x1b[90m○\x1b[0m P1", design.plan_label(p, dot="ansi"))
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertTrue(design.milestone_label(s, dot="ansi").startswith("\x1b[90m○\x1b[0m M2"))
        t = Task(id=3, milestone_id=2, title="T")
        self.assertTrue(design.task_label(t, dot="ansi").startswith("\x1b[90m○\x1b[0m T3"))
        self.assertNotIn("\x1b[", design.plan_label(p))

    def test_rich_rows_for_tui(self):
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertTrue(design.milestone_row(s).startswith("[dim]○[/]"))
        self.assertIn("[dim]M2[/]", design.milestone_row(s))
        self.assertIn("[bold]S[/]", design.milestone_row(s))
        self.assertEqual(design.milestone_row(s).count("○"), 1)
        t = Task(id=3, milestone_id=2, title="T")
        self.assertTrue(design.task_row(t).startswith("[dim]○[/]"))
        self.assertNotIn("⬜", design.task_row(t))
        p = Plan(id=1, name="N")
        self.assertEqual(design.plan_row(p).count("○"), 1)
        self.assertNotIn("⬜", design.plan_row(p))

    def test_task_row_shows_blocked_and_marked(self):
        t = Task(id=3, milestone_id=2, title="T")
        self.assertIn("[red]blocked[/]", design.task_row(t, blocked=True))
        self.assertNotIn("blocked", design.task_row(t))
        self.assertIn("✓", design.task_row(t, marked=True))
        self.assertNotIn("✓", design.task_row(t))

    def test_rich_rows_use_the_status_prefix(self):
        p = Plan(id=1, name="N", status=Status.DOING)
        s = Milestone(id=2, plan_id=1, title="S", status=Status.DOING)
        t = Task(id=3, milestone_id=2, title="T", status=Status.DOING)
        for row in (design.plan_row(p), design.milestone_row(s), design.task_row(t)):
            self.assertTrue(row.startswith(design.status_prefix("doing")))
            self.assertTrue(row.startswith("[yellow]◐[/]"))
        self.assertEqual(design.status_prefix("doing"), design.status_word("doing", "rich"))

    def test_progress_and_truncation(self):
        p = Plan(id=12, name="A very long plan title")
        row = design.plan_row(p, progress=(3, 7), width=24)
        self.assertIn("3/7", row)
        self.assertIn("…", row)
        self.assertNotIn("title", row)  # truncated before the last word
        full = design.plan_row(p, progress=(3, 7), width=80)
        self.assertIn("A very long plan title", full)
        self.assertNotIn("…", full)
        self.assertEqual(design.truncate("short", 10), "short")
        self.assertEqual(design.truncate("abcdef", 3), "ab…")

    def test_no_criteria_progress_in_labels(self):
        p = self.store.add_plan("P")
        self.store.add_criteria("plan", p.id, "done-thing", actor="t")
        c2 = self.store.add_criteria("plan", p.id, "open-thing", actor="t")
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P")
        self.store.set_criteria(c2.id, True, actor="t")
        label = design.plan_label(p, self.store)
        self.assertEqual(label, "○ P1 P")
        self.assertNotRegex(label, r"\[\d+/\d+✓\]")

    def test_plan_row_escapes_title(self):
        p = Plan(id=1, name="Ray [old]")
        self.assertEqual(design.plan_row(p), "[dim]○[/] [dim]P1[/] [bold]Ray \\[old][/]")
        self.assertNotIn("TODO", design.plan_row(p))

    def test_cli_doing_row_stays_static(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.set_status_raw("task", t.id, Status.DOING)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "list", "--tree"]), 0)
        out = buf.getvalue()
        self.assertIn("◐ T", out)
        for frame in design.SPINNER_FRAMES[1:]:
            self.assertNotIn(frame, out)

    def test_cli_uses_design_labels(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "list", "--tree"]), 0)
        lines = buf.getvalue().splitlines()
        self.assertEqual(lines[0], design.plan_label(p, self.store))
        self.assertEqual(lines[1], "  " + design.milestone_label(s, self.store))
        self.assertEqual(lines[2], "    " + design.task_label(t, self.store))

    def test_help_single_source(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(lpui_main(["--db", self.db, "help"]), 0)
        self.assertEqual(buf.getvalue().strip(), commands.HELP_TEXT.strip())
        try:
            from lazyplan.screens import HelpScreen  # needs textual installed
        except ImportError:
            HelpScreen = None
        if HelpScreen is not None:
            self.assertEqual(HelpScreen.HELP.strip(), commands.HELP_TEXT.strip())

    def test_keymap_mirrors_help(self):
        for key, _action, _surface in commands.KEYMAP:
            parts = [p.strip().split()[0] for p in key.split(",")]
            self.assertTrue(any(p and p in commands.HELP_TEXT for p in parts), key)

    def test_bindings_match_keymap(self):
        try:
            from lazyplan.tui import LazyplanApp  # needs textual installed
        except ImportError:
            self.skipTest("textual not installed")
            return
        aliases = {"question_mark": "?", "slash": "/"}
        keys = set()
        for b in LazyplanApp.BINDINGS:
            keys.update(aliases.get(k.strip(), k.strip()) for k in b.key.split(","))
        table = " ".join(k for k, _a, _s in commands.KEYMAP)
        for key in keys:
            self.assertIn(key, table, key)
        self.assertIn("?", table)
        self.assertIn("n", table)
        self.assertIn("s", table)

    def test_message_helpers(self):
        self.assertEqual(design.msg_not_found("task", 7), "task 7 not found")
        self.assertTrue(design.msg_error(ValueError("x")).startswith("error:"))
        for const in (design.EMPTY_NO_PLANS, design.EMPTY_FEED):
            self.assertTrue(isinstance(const, str) and len(const) > 0)
        self.assertIn("n", design.EMPTY_NO_PLANS)

    def test_palette_sections_cover_every_command_once(self):
        ids = [cid for cid, _ in design.PALETTE_COMMANDS]
        sectioned = [cid for _, cids in design.PALETTE_SECTIONS for cid in cids]
        self.assertEqual(sorted(sectioned), sorted(ids))
        self.assertEqual(len(sectioned), len(set(sectioned)))
        self.assertEqual(len(design.PALETTE_SECTIONS), 4)

    def test_commits_chip(self):
        self.assertEqual(design.commits_chip(None), "")
        self.assertEqual(design.commits_chip([]), "")
        sha = "a" * 40
        self.assertEqual(design.commits_chip([sha]), "[dim]aaaaaaaaaaaa[/]")
        self.assertEqual(
            design.commits_chip([sha, "b" * 40]),
            "[dim]aaaaaaaaaaaa[/] [dim]bbbbbbbbbbbb[/]",
        )

    def test_source_marker(self):
        self.assertEqual(design.SOURCE_MARKER, "⎇")
        self.assertEqual(len(design.SOURCE_MARKER), 1)
        self.assertEqual(design.source_marker(), "")
        self.assertIn(design.SOURCE_MARKER, design.source_marker(1))
        self.assertIn(design.SOURCE_MARKER, design.source_marker(0, 1))
        self.assertIn(design.SOURCE_MARKER, design.source_marker(0, 0, 1))
        self.assertFalse(design.has_source())
        self.assertTrue(design.has_source(0, 0, 1))
        p = Plan(id=1, name="N")
        self.assertNotIn(design.SOURCE_MARKER, design.plan_row(p))
        self.assertIn(design.SOURCE_MARKER, design.plan_row(p, source_counts=(1, 0, 0)))
        self.assertIn(
            design.SOURCE_MARKER,
            design.plan_row(p, source_counts=(0, 0, 0), repo_count=1),
        )

    def test_pr_chip_states(self):
        self.assertEqual(design.pr_chip(), "")
        self.assertIn("PR", design.pr_chip("open"))
        self.assertIn("green", design.pr_chip("merged"))
        self.assertIn("PR!", design.pr_chip("open", "fail"))
        self.assertIn("PR…", design.pr_chip("open", "pending"))

    def test_task_row_shows_pr_chip_only_when_cached(self):
        t = Task(id=3, milestone_id=1, title="T")
        self.assertNotIn("PR", design.task_row(t))
        self.assertIn("PR", design.task_row(t, pr_state="open"))
        self.assertIn("PR!", design.task_row(t, pr_state="open", pr_checks="fail"))

    def test_rows_show_chips_only_when_linked(self):
        p = Plan(id=1, name="N")
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
            "[dim]api[/]",
        )

    def test_plan_label_shows_linked_project(self):
        p = self.store.add_plan("P")
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P")
        self.store.add_repo_link(
            "plan", p.id, "/home/u/checkouts/api", "git@github.com:org/api.git"
        )
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P [api]")

    def test_plan_row_shows_repo_chip(self):
        p = Plan(id=1, name="N")
        self.assertEqual(design.plan_row(p), design.plan_row(p, repos=None))
        self.assertEqual(design.plan_row(p), design.plan_row(p, repos=[]))
        row = design.plan_row(p, repos=[{"repo_path": "/x/api", "repo_remote": ""}])
        self.assertIn("[dim]api[/]", row)
        s = Milestone(id=2, plan_id=1, title="S")
        self.assertEqual(design.milestone_row(s), design.milestone_row(s, links=[]))
        self.assertIn("b" * 12, design.milestone_row(s, links=["b" * 40]))
        t = Task(id=3, milestone_id=2, title="T")
        self.assertEqual(design.task_row(t), design.task_row(t, links=None))
        self.assertIn("c" * 12, design.task_row(t, links=["c" * 40]))


if __name__ == "__main__":
    unittest.main()
