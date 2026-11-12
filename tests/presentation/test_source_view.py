"""The source preview keeps diff structure and per-file counts."""

from __future__ import annotations

import unittest

from lazyplan.services.source import (
    CommitStats,
    FileStat,
    SourceCommit,
    SourceFile,
    parse_patch,
)

try:
    from rich.text import Text

    from lazyplan.presentation.tui.views.diff_render import diff_counts, render_unified
    from lazyplan.presentation.tui.views.source import commit_label, file_label
except ImportError:  # pragma: no cover - stdlib-only interpreter
    Text = None  # type: ignore[assignment]
    diff_counts = render_unified = commit_label = file_label = None  # type: ignore[assignment]

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


@unittest.skipUnless(commit_label is not None, "textual/rich not installed")
class SourceLabelTest(unittest.TestCase):
    def test_commit_label_shows_totals(self) -> None:
        commit = SourceCommit(sha="a" * 40, subject="Render diffs", files=(SourceFile("a.py"),))
        stats = CommitStats(
            files=(
                FileStat(path="a.py", status="modify", additions=3, deletions=1),
                FileStat(path="b.py", status="add", additions=5),
            )
        )
        label = Text.from_markup(commit_label(commit, stats)).plain
        self.assertIn("2 files", label)
        self.assertIn("+8", label)
        self.assertIn("-1", label)

    def test_file_label_shows_status_and_counts(self) -> None:
        added = Text.from_markup(
            file_label(
                SourceFile("app/new.py"),
                FileStat(path="app/new.py", status="add", additions=3),
            )
        ).plain
        self.assertIn("A", added)
        self.assertIn("app/new.py", added)
        self.assertIn("+3", added)
        deleted = Text.from_markup(
            file_label(
                SourceFile("app/gone.py"),
                FileStat(path="app/gone.py", status="delete", deletions=2),
            )
        ).plain
        self.assertIn("D", deleted)
        self.assertIn("-2", deleted)
        self.assertIn("gone.py", deleted)

    def test_file_label_shows_rename_and_binary(self) -> None:
        renamed = Text.from_markup(
            file_label(
                SourceFile("app/new.py"),
                FileStat(path="app/new.py", old_path="app/old.py", status="rename"),
            )
        ).plain
        self.assertIn("R", renamed)
        self.assertIn("old.py", renamed)
        self.assertIn("→", renamed)
        self.assertIn("new.py", renamed)
        binary = Text.from_markup(
            file_label(
                SourceFile("app/blob.bin"),
                FileStat(path="app/blob.bin", binary=True),
            )
        ).plain
        self.assertIn("binary", binary)

    def test_file_label_without_stats_stays_quiet(self) -> None:
        label = Text.from_markup(file_label(SourceFile("app/source.py"))).plain
        self.assertIn("app/source.py", label)
        self.assertNotIn("+", label)


if __name__ == "__main__":
    unittest.main()
