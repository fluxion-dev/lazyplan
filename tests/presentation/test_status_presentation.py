"""One status language: emoji, fallback glyph, label, and review semantics."""

from __future__ import annotations

import unittest

from lazyplan.core.entities import Status
from lazyplan.presentation.shared import design


class StatusMapTest(unittest.TestCase):
    def test_every_state_has_an_emoji_glyph_and_label(self) -> None:
        expected = {
            "todo": ("📝", "○", "not-started"),
            "doing": ("🔨", "◐", "doing"),
            "review": ("🔍", "?", "review"),
            "blocked": ("🚧", "!", "blocked"),
            "done": ("✅", "●", "done"),
        }
        for state, (emoji, glyph, label) in expected.items():
            with self.subTest(state=state):
                self.assertEqual(design.status_mark(state), emoji)
                self.assertEqual(design.status_mark(state, emoji=False), glyph)
                self.assertEqual(design.status_label(state), label)
                self.assertEqual(design.STATUS_EMOJI[state], emoji)
                self.assertEqual(design.STATUS_FALLBACK[state], glyph)
                self.assertEqual(design.STATUS_LABEL[state], label)

    def test_unknown_state_uses_the_review_mark(self) -> None:
        self.assertEqual(design.status_mark("mystery"), "🔍")
        self.assertEqual(design.status_mark("mystery", emoji=False), "?")

    def test_lifecycle_status_accepts_the_enum(self) -> None:
        self.assertEqual(design.status_mark(Status.DOING), "🔨")
        self.assertEqual(design.status_mark(Status.DONE), "✅")

    def test_fallback_glyphs_are_one_cell(self) -> None:
        for state in design.STATUS_FALLBACK:
            with self.subTest(state=state):
                self.assertEqual(len(design.status_mark(state, emoji=False)), 1)

    def test_emoji_are_two_cells(self) -> None:
        try:
            from rich.cells import cell_len
        except ImportError:  # pragma: no cover - rich ships with the TUI venv only
            self.skipTest("rich not installed")

        for state in design.STATUS_EMOJI:
            with self.subTest(state=state):
                self.assertEqual(cell_len(design.status_mark(state)), 2)


class StatusStateTest(unittest.TestCase):
    def test_plain_statuses_map_one_to_one(self) -> None:
        self.assertEqual(design.status_state(Status.TODO), "todo")
        self.assertEqual(design.status_state(Status.DOING), "doing")
        self.assertEqual(design.status_state(Status.DONE), "done")

    def test_blocked_wins_over_everything(self) -> None:
        self.assertEqual(design.status_state(Status.DONE, blocked=True), "blocked")
        self.assertEqual(design.status_state(Status.DOING, blocked=True, attention=True), "blocked")

    def test_plan_review_panel_makes_a_done_plan_review(self) -> None:
        self.assertEqual(design.status_state(Status.DONE, review=True), "review")
        self.assertEqual(design.status_state(Status.DOING, review=True), "review")

    def test_done_task_stays_done(self) -> None:
        self.assertEqual(design.status_state(Status.DONE, attention=True), "done")

    def test_attention_marks_open_work_as_review(self) -> None:
        self.assertEqual(design.status_state(Status.DOING, attention=True), "review")
        self.assertEqual(design.status_state(Status.TODO, attention=True), "review")

    def test_review_and_blocked_can_be_passed_as_states(self) -> None:
        self.assertEqual(design.status_state("review"), "review")
        self.assertEqual(design.status_state("blocked"), "blocked")


class EmojiSupportTest(unittest.TestCase):
    def test_emoji_need_a_wide_terminal(self) -> None:
        self.assertFalse(design.emoji_enabled(design.EMOJI_MIN_WIDTH - 1, ascii_safe=False))
        self.assertTrue(design.emoji_enabled(design.EMOJI_MIN_WIDTH, ascii_safe=False))

    def test_ascii_safe_wins_at_any_width(self) -> None:
        for width in (40, 80, 160, None):
            with self.subTest(width=width):
                self.assertFalse(design.emoji_enabled(width, ascii_safe=True))

    def test_wide_utf8_gets_emoji(self) -> None:
        self.assertTrue(design.emoji_enabled(120, ascii_safe=False))

    def test_dumb_terminal_is_ascii_safe(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"TERM": "dumb"}):
            self.assertTrue(design.ascii_safe_environment())
        with mock.patch.dict(os.environ, {"TERM": "xterm-256color"}):
            self.assertFalse(design.ascii_safe_environment())


class CliStatusWordTest(unittest.TestCase):
    def test_plain_cli_glyph_map_is_unchanged(self) -> None:
        self.assertEqual(design.status_word("todo"), "○")
        self.assertEqual(design.status_word("doing"), "◐")
        self.assertEqual(design.status_word("done"), "●")
        self.assertEqual(design.STATUS_GLYPH, {"todo": "○", "doing": "◐", "done": "●"})


if __name__ == "__main__":
    unittest.main()
