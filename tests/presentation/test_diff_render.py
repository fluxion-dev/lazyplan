"""Unified diff rows carry file status, tints, folds, and emphasis."""

from __future__ import annotations

import unittest

try:
    from rich.cells import cell_len
    from rich.text import Text

    from lazyplan.presentation.tui.theme.tokens import DARK_TOKENS, LIGHT_TOKENS, VOID_TOKENS
    from lazyplan.presentation.tui.views.diff_render import (
        DiffOptions,
        DiffPalette,
        render_unified,
    )
    from lazyplan.presentation.tui.views.diff_split import render_split
    from lazyplan.services.source import parse_patch
except ImportError:  # pragma: no cover - stdlib-only interpreter
    DiffOptions = DiffPalette = Text = cell_len = None  # type: ignore[assignment]
    render_split = render_unified = parse_patch = None  # type: ignore[assignment]
    DARK_TOKENS = LIGHT_TOKENS = VOID_TOKENS = None  # type: ignore[assignment]

PATCH = (
    "diff --git a/old.py b/new.py\n"
    "similarity index 90%\n"
    "rename from old.py\n"
    "rename to new.py\n"
    "--- a/old.py\n"
    "+++ b/new.py\n"
    "@@ -1 +1 @@ def trail():\n"
    "-value = 1\n"
    "+value = 2\n"
    "diff --git a/gone.py b/gone.py\n"
    "deleted file mode 100644\n"
    "--- a/gone.py\n"
    "+++ /dev/null\n"
    "@@ -1 +0,0 @@\n"
    "-gone\n"
    "diff --git a/blob.bin b/blob.bin\n"
    "Binary files a/blob.bin and b/blob.bin differ\n"
)

FOLD_PATCH = (
    "diff --git a/a.txt b/a.txt\n"
    "--- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1,9 +1,9 @@\n"
    " one\n"
    " two\n"
    " three\n"
    " four\n"
    " five\n"
    " six\n"
    " seven\n"
    " eight\n"
    "-nine\n"
    "+NINE\n"
)

WRAP_PATCH = (
    "diff --git a/a.txt b/a.txt\n"
    "--- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1 +1 @@\n"
    "-short\n"
    "+" + "word " * 30 + "\n"
)

ADD_PATCH = (
    "diff --git a/new.txt b/new.txt\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/new.txt\n"
    "@@ -0,0 +1,2 @@\n"
    "+one\n"
    "+two\n"
)

CONTEXT_PATCH = (
    "diff --git a/a.txt b/a.txt\n"
    "--- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1,3 +1,3 @@\n"
    " same\n"
    "-old\n"
    "+new\n"
    " tail\n"
)

LONG_PATH = "src/" + "very-long-directory/" * 8 + "file.py"
LONG_PATCH = (
    f"diff --git a/{LONG_PATH} b/{LONG_PATH}\n"
    f"--- a/{LONG_PATH}\n"
    f"+++ b/{LONG_PATH}\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)

UNICODE_PATCH = (
    "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+\twide 界\n"
)


def _plain(rows: list[str]) -> list[str]:
    return [Text.from_markup(row).plain for row in rows]


@unittest.skipUnless(render_unified is not None, "textual/rich not installed")
class UnifiedRenderTest(unittest.TestCase):
    def test_file_bars_show_status_counts_and_rename(self) -> None:
        plain = _plain(render_unified(parse_patch(PATCH), 90))
        joined = "\n".join(plain)
        self.assertIn("R old.py → new.py", joined)
        self.assertIn("D gone.py", joined)
        self.assertIn("M blob.bin", joined)
        self.assertIn("binary", joined)
        self.assertIn("+1", joined)
        self.assertIn("-1", joined)

    def test_add_and_remove_rows_are_tinted(self) -> None:
        rows = render_unified(parse_patch(PATCH), 90)
        added = next(row for row in rows if "+ value" in Text.from_markup(row).plain)
        removed = next(row for row in rows if "- value" in Text.from_markup(row).plain)
        self.assertIn("on #", added)
        self.assertIn("on #", removed)

    def test_changed_words_carry_emphasis(self) -> None:
        palette = DiffPalette(emphasis_add="EMPH_A", emphasis_remove="EMPH_R")
        rows = render_unified(parse_patch(PATCH), 90, palette=palette)
        self.assertTrue(any("[EMPH_R]" in row for row in rows))
        self.assertTrue(any("[EMPH_A]" in row for row in rows))

    def test_long_context_is_folded_with_a_count(self) -> None:
        rows = render_unified(parse_patch(FOLD_PATCH), 90)
        plain = "\n".join(_plain(rows))
        self.assertIn("unchanged lines", plain)
        self.assertNotIn("five", plain)

    def test_fold_off_keeps_every_context_line(self) -> None:
        rows = render_unified(
            parse_patch(FOLD_PATCH),
            90,
            options=DiffOptions(fold=False),
        )
        plain = "\n".join(_plain(rows))
        self.assertIn("five", plain)
        self.assertNotIn("unchanged lines", plain)

    def test_long_lines_wrap_with_a_marker(self) -> None:
        rows = render_unified(parse_patch(WRAP_PATCH), 48)
        plain = "\n".join(_plain(rows))
        self.assertIn("↳", plain)
        self.assertGreaterEqual(plain.count("word"), 2)

    def test_wrap_off_truncates_with_an_ellipsis(self) -> None:
        rows = render_unified(
            parse_patch(WRAP_PATCH),
            48,
            options=DiffOptions(wrap=False),
        )
        plain = "\n".join(_plain(rows))
        self.assertIn("…", plain)
        self.assertNotIn("↳", plain)

    def test_empty_files_get_an_explicit_message(self) -> None:
        self.assertEqual(render_unified((), 80), ["[dim]no textual changes[/]"])

    def test_palette_from_theme_reads_tokens(self) -> None:
        palette = DiffPalette.from_theme(
            {
                "lp-diff-add": "#001100",
                "lp-diff-remove": "#110000",
                "lp-diff-add-bg": "#002200",
                "lp-diff-emphasis-add": "#003300",
                "lp-syntax-keyword": "#004400",
                "lp-text-faint": "#333333",
            }
        )
        self.assertEqual(palette.add, "#001100")
        self.assertEqual(palette.add_bg, "#002200")
        self.assertIn("#003300", palette.emphasis_add)
        self.assertEqual(palette.syntax["keyword"], "#004400")
        self.assertEqual(palette.gutter, "#333333")

    def test_narrow_width_does_not_crash(self) -> None:
        rows = render_unified(parse_patch(WRAP_PATCH), 1)
        self.assertTrue(rows)

    def test_every_row_is_valid_markup(self) -> None:
        for row in render_unified(parse_patch(PATCH), 90):
            Text.from_markup(row)
        result = render_split(parse_patch(PATCH), 100)
        for row in result.rows:
            Text.from_markup(row)

    def test_long_path_fits_the_pane_width(self) -> None:
        row = render_unified(parse_patch(LONG_PATCH), 60)[0]
        self.assertLessEqual(cell_len(Text.from_markup(row).plain), 60)
        self.assertIn("…", Text.from_markup(row).plain)

    def test_tabs_and_wide_characters_survive(self) -> None:
        plain = "\n".join(_plain(render_unified(parse_patch(UNICODE_PATCH), 80)))
        self.assertIn("    wide 界", plain)


@unittest.skipUnless(render_split is not None, "textual/rich not installed")
class SplitRenderTest(unittest.TestCase):
    def test_replacement_pairs_old_and_new_columns(self) -> None:
        result = render_split(parse_patch(PATCH), 100)
        self.assertTrue(result.available)
        plain = _plain(list(result.rows))
        paired = next(row for row in plain if "value = 1" in row and "value = 2" in row)
        left, right = paired.split("│", 1)
        self.assertIn("value = 1", left)
        self.assertIn("value = 2", right)

    def test_add_only_line_leaves_the_left_blank(self) -> None:
        result = render_split(parse_patch(ADD_PATCH), 100)
        plain = _plain(list(result.rows))
        row = next(item for item in plain if "+ one" in item)
        left, right = row.split("│", 1)
        self.assertEqual(left.strip(), "")
        self.assertIn("+ one", right)

    def test_remove_only_line_leaves_the_right_blank(self) -> None:
        result = render_split(parse_patch(PATCH), 100)
        plain = _plain(list(result.rows))
        row = next(item for item in plain if "- gone" in item)
        left, right = row.split("│", 1)
        self.assertIn("- gone", left)
        self.assertEqual(right.strip(), "")

    def test_context_appears_in_both_columns(self) -> None:
        result = render_split(parse_patch(CONTEXT_PATCH), 100)
        plain = _plain(list(result.rows))
        row = next(item for item in plain if " same" in item and "│" in item)
        left, right = row.split("│", 1)
        self.assertIn("same", left)
        self.assertIn("same", right)

    def test_long_context_folds_in_split_mode(self) -> None:
        result = render_split(parse_patch(FOLD_PATCH), 100)
        plain = "\n".join(_plain(list(result.rows)))
        self.assertIn("unchanged lines", plain)

    def test_long_lines_wrap_inside_a_column(self) -> None:
        result = render_split(parse_patch(WRAP_PATCH), 100)
        plain = "\n".join(_plain(list(result.rows)))
        self.assertIn("↳", plain)

    def test_narrow_pane_reports_the_minimum_width(self) -> None:
        result = render_split(parse_patch(PATCH), 50)
        self.assertFalse(result.available)
        self.assertIn("64", result.detail)

    def test_empty_split_has_a_message(self) -> None:
        result = render_split((), 100)
        self.assertTrue(result.available)
        self.assertEqual(result.rows, ("[dim]no textual changes[/]",))


@unittest.skipUnless(DARK_TOKENS is not None, "textual not installed")
class ThemeTokenTest(unittest.TestCase):
    def test_every_theme_carries_diff_and_syntax_tokens(self) -> None:
        def keys(theme: dict[str, str]) -> set[str]:
            return {name for name in theme if name.startswith(("lp-diff-", "lp-syntax-"))}

        expected = keys(DARK_TOKENS)
        self.assertTrue(expected)
        self.assertEqual(keys(LIGHT_TOKENS), expected)
        self.assertEqual(keys(VOID_TOKENS), expected)


if __name__ == "__main__":
    unittest.main()
