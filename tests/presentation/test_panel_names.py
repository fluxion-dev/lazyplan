"""The plan tree panels name themselves and empty panes stay hidden."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.presentation.shared import design

try:
    from lazyplan.presentation.tui.app import create_app
except ImportError:  # pragma: no cover - stdlib-only interpreter
    create_app = None  # type: ignore[assignment]


class TestPanelCopy(unittest.TestCase):
    def test_panel_titles_and_empty_states_use_plan_names(self) -> None:
        self.assertEqual(design.PANEL_PLAN_QUEUE_TITLE, "plan queue")
        self.assertEqual(design.PANEL_PLAN_REVIEW_TITLE, "plan review")
        self.assertEqual(
            design.empty_state(design.EMPTY_PLAN_QUEUE_TITLE, design.EMPTY_PLAN_QUEUE_HINT),
            "[bold]No plans in the plan queue[/]\n[dim]press n to create one[/]",
        )

    def test_cli_empty_state_keeps_its_wording(self) -> None:
        self.assertEqual(design.EMPTY_NO_PLANS_TITLE, "No active plans")
        self.assertEqual(design.EMPTY_NO_PLANS_HINT, "press n to create one")


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestMountedPanelCopy(unittest.IsolatedAsyncioTestCase):
    async def test_empty_journal_shows_only_the_plan_queue(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "panel.db"))
            async with app.run_test(size=(120, 35)) as pilot:
                await pilot.pause()
                self.assertEqual(
                    app.query_one("#plans-active").border_title,
                    f" {design.PANEL_PLAN_QUEUE_TITLE} ",
                )
                self.assertEqual(
                    app.query_one("#plans-finished").border_title,
                    f" {design.PANEL_PLAN_REVIEW_TITLE} ",
                )
                self.assertIn(
                    "No plans in the plan queue",
                    str(app.query_one("#tree-empty").render()),
                )
                self.assertTrue(app.query_one("#plans-active").display)
                self.assertFalse(app.query_one("#plans-finished").display)
                self.assertFalse(app.query_one("#agents").display)
                self.assertFalse(app.query_one("#git").display)


if __name__ == "__main__":
    unittest.main()
