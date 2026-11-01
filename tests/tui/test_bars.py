"""Status and hint bars stay one row and keep their key data."""

from __future__ import annotations

import unittest

from lazyplan.help import hint_bar
from lazyplan.tui.views.bars import status_bar


class BarTest(unittest.TestCase):
    def test_status_bar_carries_the_core_counts(self) -> None:
        bar = status_bar(repo="repo", plans=3, open_tasks=9, doing=1, width=120)
        text = bar.plain
        self.assertIn("repo", text)
        self.assertIn("3 plans", text)
        self.assertIn("9 open", text)
        self.assertIn("1 doing", text)

    def test_status_bar_truncates_to_width(self) -> None:
        bar = status_bar(repo="a" * 40, plans=1, open_tasks=1, doing=0, width=20)
        self.assertLessEqual(bar.cell_len, 20)

    def test_status_bar_marks_filters_and_updates(self) -> None:
        bar = status_bar(
            repo="repo",
            plans=1,
            open_tasks=1,
            doing=0,
            status="doing",
            source="claims",
            filter_text="needle",
            update="update v9.9.9",
            width=160,
        )
        text = bar.plain
        for part in ("status doing", "source claims", "filter", "needle", "update v9.9.9"):
            self.assertIn(part, text)

    def test_hint_bar_markup_wraps_keys(self) -> None:
        text = hint_bar(120, markup=True)
        self.assertIn("[reverse] n [/]", text)
        self.assertIn("commands", text)
        self.assertNotIn("[reverse]", hint_bar(120))


if __name__ == "__main__":
    unittest.main()
