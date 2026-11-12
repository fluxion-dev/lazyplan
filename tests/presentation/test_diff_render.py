"""Unified diff rows carry file status, tints, folds, and emphasis."""

from __future__ import annotations

import unittest

try:
    from rich.text import Text

    from lazyplan.presentation.tui.views.diff_render import (
        DiffOptions,
        DiffPalette,
        render_unified,
    )
    from lazyplan.services.source import parse_patch
except ImportError:  # pragma: no cover - stdlib-only interpreter
    DiffOptions = DiffPalette = Text = None  # type: ignore[assignment]
    render_unified = parse_patch = None  # type: ignore[assignment]

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
                "lp-text-faint": "#333333",
            }
        )
        self.assertEqual(palette.add, "#001100")
        self.assertEqual(palette.add_bg, "#002200")
        self.assertEqual(palette.gutter, "#333333")

    def test_narrow_width_does_not_crash(self) -> None:
        rows = render_unified(parse_patch(WRAP_PATCH), 1)
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
