"""Fixed-width stat slots: layout, blanks, compact forms, and drop order."""

from __future__ import annotations

import unittest

from lazyplan.design.row_stats import (
    SLOTS,
    TITLE_MIN,
    RowStats,
    render_stats,
    stats_layout,
)
from lazyplan.design.text import pr_label

try:
    from rich.text import Text
except ImportError:  # pragma: no cover - stdlib-only interpreter
    Text = None  # type: ignore[assignment,misc]


def _block_width(layout: tuple[tuple[str, bool], ...]) -> int:
    if not layout:
        return 0
    return sum(
        SLOTS[key].compact_width if compact else SLOTS[key].width for key, compact in layout
    ) + (len(layout) - 1)


class StatsLayoutTest(unittest.TestCase):
    def test_plan_layout_keeps_the_full_order_at_a_wide_width(self) -> None:
        layout = stats_layout("plan", 80, 7)

        self.assertEqual(
            [key for key, _compact in layout],
            ["progress", "commits", "pulls", "stale", "marked"],
        )
        self.assertFalse(any(compact for _key, compact in layout))

    def test_task_layout_keeps_state_stats_at_a_narrow_width(self) -> None:
        layout = stats_layout("task", 33, 6)

        self.assertEqual(
            [key for key, _compact in layout],
            ["pulls", "marked", "blocked", "claim"],
        )
        self.assertEqual(
            [compact for _key, compact in layout],
            [False, False, True, True],
        )

    def test_milestone_layout_drops_stale_before_progress(self) -> None:
        layout = stats_layout("milestone", 37, 6)

        self.assertEqual(
            [(key, compact) for key, compact in layout],
            [("progress", True), ("commits", False), ("pulls", False), ("marked", False)],
        )

    def test_task_layout_drops_stale_before_state(self) -> None:
        layout = stats_layout("task", 51, 6)
        keys = [key for key, _compact in layout]

        self.assertIn("commits", keys)
        self.assertIn("blocked", keys)
        self.assertIn("claim", keys)
        self.assertNotIn("stale", keys)

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
        full = RowStats(
            kind="task",
            commits=2,
            pr_state="open",
            marked=True,
            blocked=True,
            claim_actor="alice",
        )
        empty = RowStats(kind="task")

        full_plain = render_stats(full, layout)[1]
        empty_plain = render_stats(empty, layout)[1]

        self.assertEqual(len(full_plain), len(empty_plain))
        self.assertEqual(empty_plain.strip(), "")


@unittest.skipUnless(Text is not None, "rich not installed")
class StatsRenderTest(unittest.TestCase):
    def test_rich_and_plain_blocks_have_equal_width(self) -> None:
        stats = RowStats(
            kind="task",
            commits=2,
            pr_state="open",
            marked=True,
            blocked=True,
            claim_actor="alice",
            stale=1,
        )
        layout = stats_layout("task", 80, 7)
        rich, plain = render_stats(stats, layout)

        self.assertEqual(Text.from_markup(rich).plain, plain)
        self.assertIn("2c", plain)
        self.assertIn("PR", plain)
        self.assertIn("✓", plain)
        self.assertIn("⚑ blocked", plain)
        self.assertIn("◉ @alice", plain)

    def test_compact_forms_are_used_at_a_narrow_width(self) -> None:
        stats = RowStats(
            kind="task",
            pr_state="open",
            marked=True,
            blocked=True,
            claim_actor="alice",
        )
        layout = stats_layout("task", 33, 6)
        rich, plain = render_stats(stats, layout)

        self.assertEqual(Text.from_markup(rich).plain, plain)
        self.assertIn("⚑", plain)
        self.assertNotIn("⚑ blocked", plain)
        self.assertIn("◉ @", plain)
        self.assertLessEqual(len(plain), 19)

    def test_claim_keeps_the_expired_marker_when_truncated(self) -> None:
        stats = RowStats(
            kind="task",
            claim_actor="alice",
            claim_expired=True,
        )
        layout = (("claim", True),)
        _rich, plain = render_stats(stats, layout)

        self.assertTrue(plain.endswith("!"))
        self.assertEqual(len(plain), 8)

    def test_pr_label_matches_pr_chip_text(self) -> None:
        from lazyplan.design.text import pr_chip

        for state, checks in (
            ("", ""),
            ("open", ""),
            ("merged", ""),
            ("open", "fail"),
            ("open", "pending"),
        ):
            with self.subTest(state=state, checks=checks):
                self.assertEqual(
                    Text.from_markup(pr_chip(state, checks)).plain,
                    pr_label(state, checks),
                )


if __name__ == "__main__":
    unittest.main()
