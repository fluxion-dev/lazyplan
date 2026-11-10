"""The source preview keeps diff structure and per-file counts."""

from __future__ import annotations

import unittest

from lazyplan.services.source import parse_patch

try:
    from lazyplan.presentation.tui.views.source import diff_counts, diff_rows
except ImportError:  # pragma: no cover - stdlib-only interpreter
    diff_counts = diff_rows = None  # type: ignore[assignment]

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


@unittest.skipUnless(diff_rows is not None, "textual/rich not installed")
class SourceDiffViewTest(unittest.TestCase):
    def test_counts_added_and_removed_lines(self) -> None:
        item = parse_patch(PATCH)[0]
        self.assertEqual(diff_counts(item), (2, 1))

    def test_rows_keep_path_hunk_and_counts(self) -> None:
        rows = diff_rows(parse_patch(PATCH), 10)
        self.assertIn("a.txt", rows[0])
        self.assertIn("+2", rows[0])
        self.assertIn("-1", rows[0])
        self.assertIn("@@ -1,2 +1,3 @@", rows[1])
        self.assertTrue(any("+TWO" in row for row in rows))


if __name__ == "__main__":
    unittest.main()
