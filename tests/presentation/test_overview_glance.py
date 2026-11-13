"""The main screen stays scannable at every supported width."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from rich.text import Text
    from textual.widgets import Markdown, Static

    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    Text = None  # type: ignore[assignment,misc]
    Markdown = Static = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]

WIDTHS = (80, 100, 120, 160)
GLYPHS = ("○", "◐", "●", "◈", "◇", "▹", "▰", "▱", "!", "✓", "✗", "—", "◆", "✕", "⊘", "▶")


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestOverviewGlance(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "glance.db"))
        self.plan = self.store.add_plan(
            "Make the overview scannable",
            "What we build",
            goal="The screen should answer what this plan is before it asks to be read.",
            worktree_required=False,
        )
        self.milestone = self.store.add_milestone(
            self.plan.id, "Strip the glyphs", "Rows read as plain words."
        )
        self.task = self.store.add_task(
            self.milestone.id, "Rewrite the row grammar", "Approach and details."
        )
        self.doing = self.store.add_task(self.milestone.id, "Trim the overview", "Details.")
        self.store.set_status_raw("task", self.doing.id, Status.DOING)
        self.blocked = self.store.add_task(self.milestone.id, "Wait on review", "Details.")
        self.store.set_blocked(self.blocked.id, True, "waiting", actor="t")
        self.store.add_criteria("plan", self.plan.id, "The screen reads as words", actor="t")

    def _tree_row(self, app: object, key: tuple[str, int]) -> str:
        return Text.from_markup(app._row_labels[key]).plain  # type: ignore[attr-defined]

    async def _select(self, app: object, pilot: object, kind: str, oid: int) -> None:
        app._expanded.update(  # type: ignore[attr-defined]
            {("plan", self.plan.id), ("milestone", self.milestone.id)}
        )
        app.refresh_all()  # type: ignore[attr-defined]
        await pilot.pause()  # type: ignore[attr-defined]
        app.select_row(kind, oid)  # type: ignore[attr-defined]
        await pilot.pause()  # type: ignore[attr-defined]

    async def test_plan_glance_at_every_width(self) -> None:
        for width in WIDTHS:
            with self.subTest(width=width):
                app = create_app(str(self.store.path))
                async with app.run_test(size=(width, 40)) as pilot:
                    await pilot.pause()
                    await self._select(app, pilot, "plan", self.plan.id)
                    head = str(app.query_one("#preview-head", Static).render()).splitlines()
                    body = app.query_one("#preview-body", Markdown).source or ""
                    self.assertEqual(head[0], "Make the overview scannable")
                    self.assertEqual(len(head), 2)
                    self.assertIn(f"P{self.plan.id}", head[1])
                    self.assertIn("0/3 tasks", head[1])
                    self.assertIn("## WHY", body)
                    self.assertIn("## MILESTONES 1", body)
                    self.assertIn("The screen should answer", body)
                    for hidden in ("## APPROVAL", "## SOURCE", "## NOTES", "## WORKTREES"):
                        self.assertNotIn(hidden, body)
                    for glyph in GLYPHS:
                        self.assertNotIn(glyph, head[0] + head[1] + body)

    async def test_milestone_and_task_glance_at_every_width(self) -> None:
        for width in WIDTHS:
            with self.subTest(width=width):
                app = create_app(str(self.store.path))
                async with app.run_test(size=(width, 40)) as pilot:
                    await pilot.pause()
                    await self._select(app, pilot, "milestone", self.milestone.id)
                    milestone_body = app.query_one("#preview-body", Markdown).source or ""
                    self.assertIn("## DETAILS", milestone_body)
                    self.assertIn("## TASKS 3", milestone_body)
                    self.assertIn(f"T{self.doing.id}  Trim the overview · doing", milestone_body)
                    self.assertIn(f"T{self.blocked.id}  Wait on review · blocked", milestone_body)
                    for hidden in ("## NOTES", "## SOURCE", "## PROOF"):
                        self.assertNotIn(hidden, milestone_body)

                    await self._select(app, pilot, "task", self.task.id)
                    task_body = app.query_one("#preview-body", Markdown).source or ""
                    self.assertIn("## DETAILS", task_body)
                    self.assertIn("Approach and details.", task_body)
                    self.assertNotIn("## ACCEPTANCE", task_body)
                    self.assertNotIn("## SOURCE", task_body)

    async def test_tree_rows_and_footer_stay_words_only(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self._select(app, pilot, "plan", self.plan.id)
            plan_row = self._tree_row(app, ("plan", self.plan.id))
            self.assertIn("0/3", plan_row)
            doing_row = self._tree_row(app, ("task", self.doing.id))
            self.assertTrue(doing_row.rstrip().endswith("doing"))
            blocked_row = self._tree_row(app, ("task", self.blocked.id))
            self.assertTrue(blocked_row.rstrip().endswith("blocked"))
            for row in (plan_row, doing_row, blocked_row):
                for glyph in GLYPHS:
                    self.assertNotIn(glyph, row)
            footer = str(app.query_one("#hints").render())
            self.assertLessEqual(footer.count(" · ") + 1, 3)

    async def test_narrow_screen_keeps_the_tree_and_hides_the_overview(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            self.assertFalse(app.query_one("#side").display)
            self.assertFalse(app.query_one("#preview").display)
            self.assertTrue(app.query_one("#plans-active").display)
            self.assertFalse(app.query_one("#agents").display)
            self.assertFalse(app.query_one("#git").display)


if __name__ == "__main__":
    unittest.main()
