"""Fixed-width word slots: layout, blanks, and drop order."""

from __future__ import annotations

import unittest

from lazyplan.presentation.shared.design.row_stats import (
    SLOTS,
    TITLE_MIN,
    RowStats,
    render_stats,
    stats_layout,
)

try:
    from rich.text import Text
except ImportError:  # pragma: no cover - stdlib-only interpreter
    Text = None  # type: ignore[assignment,misc]


def _block_width(layout: tuple[str, ...]) -> int:
    if not layout:
        return 0
    return sum(SLOTS[key].width for key in layout) + (len(layout) - 1)


class StatsLayoutTest(unittest.TestCase):
    def test_plan_layout_keeps_the_count_and_the_state_word_at_a_wide_width(self) -> None:
        layout = stats_layout("plan", 80, 7)

        self.assertEqual(layout, ("progress", "state"))

    def test_task_layout_is_state_only(self) -> None:
        layout = stats_layout("task", 33, 6)

        self.assertEqual(layout, ("state",))

    def test_milestone_layout_keeps_the_state_word_at_a_narrow_width(self) -> None:
        layout = stats_layout("milestone", 25, 6)

        self.assertEqual(layout, ("state",))

    def test_layout_never_exceeds_the_width_budget(self) -> None:
        for kind in ("plan", "milestone", "task"):
            for width in range(20, 90):
                for prefix in (6, 7):
                    with self.subTest(kind=kind, width=width, prefix=prefix):
                        layout = stats_layout(kind, width, prefix)
                        self.assertLessEqual(
                            prefix + TITLE_MIN + _block_width(layout),
                            width,
                        )

    def test_missing_stats_reserve_blank_slots(self) -> None:
        layout = stats_layout("task", 80, 7)
        full = RowStats(state="review")
        empty = RowStats()

        full_plain = render_stats(full, layout)[1]
        empty_plain = render_stats(empty, layout)[1]

        self.assertEqual(len(full_plain), len(empty_plain))
        self.assertEqual(empty_plain.strip(), "")


@unittest.skipUnless(Text is not None, "rich not installed")
class StatsRenderTest(unittest.TestCase):
    def test_rich_and_plain_blocks_have_equal_width(self) -> None:
        stats = RowStats(state="review")
        layout = stats_layout("task", 80, 7)
        rich, plain = render_stats(stats, layout)

        self.assertEqual(Text.from_markup(rich).plain, plain)
        self.assertIn("review", plain)
        self.assertNotIn("!", plain)
        self.assertNotIn("▰", plain)
        self.assertNotIn("PR", plain)

    def test_state_slot_renders_only_when_set(self) -> None:
        layout = ("state",)
        rich, plain = render_stats(RowStats(state="blocked"), layout)
        self.assertEqual(Text.from_markup(rich).plain, plain)
        self.assertIn("blocked", plain)
        self.assertEqual(render_stats(RowStats(), layout)[1].strip(), "")

    def test_progress_is_a_count_without_a_bar(self) -> None:
        stats = RowStats(progress=(1, 4), state="doing")
        layout = stats_layout("plan", 80, 7)
        rich, plain = render_stats(stats, layout)

        self.assertEqual(Text.from_markup(rich).plain, plain)
        self.assertIn("1/4", plain)
        self.assertIn("doing", plain)
        self.assertNotIn("▰", plain)
        self.assertNotIn("▱", plain)


if __name__ == "__main__":
    unittest.main()
