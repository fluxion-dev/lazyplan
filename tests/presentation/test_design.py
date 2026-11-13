"""Internal-consistency tests: CLI, TUI, palette, and help share one design."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from lazyplan.core.entities import Milestone, Plan, Status, Task
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.presentation.shared import design
from lazyplan.presentation.shared import help as help_mod
from lazyplan.store import Store

try:
    from rich.text import Text
except ImportError:  # pragma: no cover - stdlib-only interpreter
    Text = None  # type: ignore[assignment,misc]


class TestDesignSystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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
        self.assertTrue(design.milestone_row(s).startswith("[dim]M2[/] "))
        self.assertIn("[bold]S[/]", design.milestone_row(s))
        self.assertNotIn("○", design.milestone_row(s))
        t = Task(id=3, milestone_id=2, title="T")
        self.assertTrue(design.task_row(t).startswith("[dim]T3[/] "))
        self.assertNotIn("⬜", design.task_row(t))
        p = Plan(id=1, name="N")
        self.assertTrue(design.plan_row(p).startswith("[dim]P1[/] "))
        self.assertNotIn("⬜", design.plan_row(p))

    def test_task_row_hides_claim_and_blocked_detail(self):
        t = Task(id=3, milestone_id=2, title="T")
        row = design.task_row(t)
        self.assertIn("T3", row)
        self.assertIn("[bold]T[/]", row)
        self.assertNotIn("⚑", row)
        self.assertNotIn("◉", row)
        self.assertNotIn("blocked", row)

    @unittest.skipUnless(Text is not None, "rich not installed")
    def test_task_row_reads_as_id_title_and_words(self):
        t = Task(id=3, milestone_id=2, title="Compact title")

        plain = Text.from_markup(design.task_row(t, width=80)).plain

        self.assertEqual(plain.rstrip(), "T3 Compact title")
        for stat in ("○", "◐", "●", "⚑", "◉", "▰", "▱", "@", "/", "!"):
            self.assertNotIn(stat, plain)

    @unittest.skipUnless(Text is not None, "rich not installed")
    def test_task_row_marks_attention_with_one_word(self):
        t = Task(id=3, milestone_id=2, title="Compact title")

        plain = Text.from_markup(design.task_row(t, attention=True, width=80)).plain

        self.assertTrue(plain.rstrip().endswith("review"))
        self.assertIn("T3 Compact title", plain)
        self.assertEqual(plain.count("review"), 1)
        self.assertNotIn("!", plain)

    @unittest.skipUnless(Text is not None, "rich not installed")
    def test_task_row_truncates_to_the_row_width(self):
        t = Task(id=3, milestone_id=2, title="A very long task title that will not fit")

        for width in (12, 20, 33, 80):
            with self.subTest(width=width):
                plain = Text.from_markup(design.task_row(t, width=width)).plain
                self.assertEqual(len(plain), width)
                self.assertIn("T3", plain)

        narrow = Text.from_markup(design.task_row(t, width=20)).plain
        self.assertIn("…", narrow)

    @unittest.skipUnless(Text is not None, "rich not installed")
    def test_task_row_gives_the_freed_slots_to_the_title(self):
        title = "A title long enough to be cut by the old slots"
        t = Task(id=3, milestone_id=2, title=title)

        plain = Text.from_markup(design.task_row(t, width=60)).plain

        self.assertIn(title, plain)
        self.assertNotIn("…", plain)

    def test_task_label_keeps_blocked_and_claim_detail(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.set_blocked(t.id, True, "waiting on design", actor="t")

        label = design.task_label(self.store.get_task(t.id), self.store)

        self.assertTrue(label.startswith("○ T"))
        self.assertIn("[blocked]", label)

    def test_rich_rows_show_doing_as_a_word(self):
        p = Plan(id=1, name="N", status=Status.DOING)
        s = Milestone(id=2, plan_id=1, title="S", status=Status.DOING)
        t = Task(id=3, milestone_id=2, title="T", status=Status.DOING)
        for row in (design.plan_row(p), design.milestone_row(s), design.task_row(t)):
            self.assertTrue(row.rstrip().endswith("doing"))
            self.assertNotIn("◐", row)

    def test_progress_and_truncation(self):
        p = Plan(id=12, name="A very long plan title")
        row = design.plan_row(p, progress=(3, 7), width=24)
        self.assertIn("…", row)
        self.assertNotIn("▰", row)
        self.assertNotIn("title", row)  # truncated before the last word
        full = design.plan_row(p, progress=(3, 7), width=80)
        self.assertIn("A very long plan title", full)
        self.assertIn("3/7", full)
        self.assertNotIn("…", full)
        self.assertEqual(design.truncate("short", 10), "short")
        self.assertEqual(design.truncate("abcdef", 3), "ab…")

    @unittest.skipUnless(Text is not None, "rich not installed")
    def test_plan_rows_keep_the_stats_block_start(self):
        p = Plan(id=1, name="Plan")
        width = 80
        first = Text.from_markup(design.plan_row(p, progress=(3, 7), width=width)).plain
        second = Text.from_markup(
            design.plan_row(
                p,
                progress=(3, 7),
                attention=True,
                width=width,
            )
        ).plain

        self.assertEqual(len(first), width)
        self.assertEqual(len(second), width)
        self.assertEqual(first.index("3/7"), second.index("3/7"))

    def test_no_criteria_progress_in_labels(self):
        p = self.store.add_plan("P")
        self.store.add_criteria("plan", p.id, "done-thing", actor="t")
        c2 = self.store.add_criteria("plan", p.id, "open-thing", actor="t")
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P")
        self.store.update_criterion(c2.id, done=True, actor="t")
        label = design.plan_label(p, self.store)
        self.assertEqual(label, "○ P1 P")
        self.assertNotRegex(label, r"\[\d+/\d+✓\]")

    def test_plan_row_marks_a_registered_worktree(self):
        p = Plan(id=1, name="Plan")
        self.assertIn("wt", design.plan_row(p, worktrees=1, width=80))
        self.assertNotIn("wt", design.plan_row(p, worktrees=0, width=80))

    def test_plan_row_escapes_title(self):
        p = Plan(id=1, name="Ray [old]")
        row = design.plan_row(p, width=80)
        self.assertIn(r"[bold]Ray \[old][/]", row)
        self.assertNotIn("TODO", row)

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
        self.assertNotIn("⠋", out)

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
        self.assertEqual(buf.getvalue().strip(), help_mod.HELP_TEXT.strip())
        try:
            from lazyplan.presentation.tui.screens import HelpScreen  # needs textual installed
        except ImportError:
            HelpScreen = None
        if HelpScreen is not None:
            self.assertEqual(HelpScreen.HELP.strip(), help_mod.HELP_TEXT.strip())

    def test_keymap_mirrors_help(self):
        for key, _action, _surface in help_mod.KEYMAP:
            parts = [p.strip().split()[0] for p in key.split(",")]
            self.assertTrue(any(p and p in help_mod.HELP_TEXT for p in parts), key)

    def test_bindings_match_keymap(self):
        try:
            from lazyplan.presentation.tui import LazyplanApp  # needs textual installed
        except ImportError:
            self.skipTest("textual not installed")
            return
        aliases = {"question_mark": "?", "slash": "/"}
        keys = set()
        for b in LazyplanApp.BINDINGS:
            keys.update(aliases.get(k.strip(), k.strip()) for k in b.key.split(","))
        table = " ".join(k for k, _a, _s in help_mod.KEYMAP)
        for key in keys:
            self.assertIn(key, table, key)
        self.assertIn("?", table)
        self.assertIn("n", table)
        self.assertIn("s", table)

    def test_hint_bar_names_at_most_three_keys(self):
        for width in (20, 40, 80, 120):
            with self.subTest(width=width):
                bar = help_mod.hint_bar(width)
                self.assertLessEqual(bar.count(" · ") + 1, 3)
                self.assertTrue(bar)

    def test_message_helpers(self):
        self.assertEqual(design.msg_not_found("task", 7), "task 7 not found")
        self.assertTrue(design.msg_error(ValueError("x")).startswith("error:"))
        for const in (design.EMPTY_NO_PLANS, design.EMPTY_FEED):
            self.assertTrue(isinstance(const, str) and len(const) > 0)
        self.assertIn("n", design.EMPTY_NO_PLANS)

    def test_empty_state_is_a_capitalized_title_and_next_step(self):
        text = design.empty_state("no active plans", "press n to create one")
        self.assertEqual(text, "[bold]No active plans[/]\n[dim]press n to create one[/]")
        self.assertEqual(text.count("\n"), 1)

    def test_palette_sections_cover_every_command_once(self):
        ids = [cid for cid, _ in design.PALETTE_COMMANDS]
        sectioned = [cid for _, cids in design.PALETTE_SECTIONS for cid in cids]
        self.assertEqual(sorted(sectioned), sorted(ids))
        self.assertEqual(len(sectioned), len(set(sectioned)))
        self.assertEqual(len(design.PALETTE_SECTIONS), 4)

    def test_rows_render_progress_and_attention_not_source_counts(self):
        p = Plan(id=1, name="N")
        row = design.plan_row(p, progress=(2, 5), attention=True)
        self.assertIn("2/5", row)
        self.assertIn("review", row)
        self.assertNotIn("!", row)
        self.assertNotIn("1c", row)
        self.assertNotIn("PR", row)

    def test_pr_chip_states(self):
        self.assertEqual(design.pr_chip(), "")
        self.assertIn("PR", design.pr_chip("open"))
        self.assertIn("green", design.pr_chip("merged"))
        self.assertIn("PR!", design.pr_chip("open", "fail"))
        self.assertIn("PR…", design.pr_chip("open", "pending"))

    def test_task_row_shows_attention_not_pr_or_commit_counts(self):
        t = Task(id=3, milestone_id=1, title="T")
        bare = design.task_row(t)
        hot = design.task_row(t, attention=True)
        self.assertNotIn("PR", bare)
        self.assertNotIn("1c", bare)
        self.assertIn("review", hot)
        self.assertNotIn("!", hot)

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

    def test_plan_label_shows_linked_project(self):
        p = self.store.add_plan("P")
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P")
        self.store.add_repo_link(
            "plan", p.id, "/home/u/checkouts/api", "git@github.com:org/api.git"
        )
        self.assertEqual(design.plan_label(p, self.store), "○ P1 P [api]")

    def test_action_bar_reverses_only_the_primary_action(self):
        text = design.action_bar(
            ("o", "open"),
            [("o", "open"), ("y", "copy"), ("", "ignored")],
        )
        self.assertIn("[reverse] o [/]open", text)
        self.assertIn("[dim]y[/] copy", text)
        self.assertNotIn("ignored", text)
        self.assertEqual(design.action_bar(None, []), "esc back")


if __name__ == "__main__":
    unittest.main()
