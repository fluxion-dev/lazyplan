"""The source preview keeps diff structure and per-file counts."""

from __future__ import annotations

import unittest

from lazyplan.services.source import parse_patch

try:
    from rich.text import Text

    from lazyplan.presentation.tui.views.diff_render import diff_counts, render_unified
except ImportError:  # pragma: no cover - stdlib-only interpreter
    Text = None  # type: ignore[assignment]
    diff_counts = render_unified = None  # type: ignore[assignment]

PATCH = (
    "diff --git a/a.txt b/a.txt\n"
    "index 111..222 100644\n"
    "--- a/a.txt\n"
    "+++ b/a.txt\n"
    "@@ -1,2 +1,3 @@ section\n"
    " one\n"
    "-two\n"
    "+TWO\n"
    "+three\n"
)


@unittest.skipUnless(render_unified is not None, "textual/rich not installed")
class SourceDiffViewTest(unittest.TestCase):
    def test_counts_added_and_removed_lines(self) -> None:
        item = parse_patch(PATCH)[0]
        self.assertEqual(diff_counts(item), (2, 1))

    def test_rows_keep_path_hunk_and_counts(self) -> None:
        rows = render_unified(parse_patch(PATCH), 80)
        plain = [Text.from_markup(row).plain for row in rows]
        self.assertIn("a.txt", plain[0])
        self.assertIn("+2", plain[0])
        self.assertIn("-1", plain[0])
        self.assertIn("@@ -1,2 +1,3 @@", plain[1])
        self.assertIn("section", plain[1])
        self.assertTrue(any("+ TWO" in row for row in plain))

    def test_rows_use_tinted_add_and_remove_backgrounds(self) -> None:
        rows = render_unified(parse_patch(PATCH), 80)
        added = next(row for row in rows if "TWO" in Text.from_markup(row).plain)
        removed = next(row for row in rows if "two" in Text.from_markup(row).plain)
        self.assertIn("on #", added)
        self.assertIn("on #", removed)


if __name__ == "__main__":
    unittest.main()
