"""The work cards live in one left column; the right column is the overview."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


EXPECTED_LEFT = ("plans-active", "agents", "plans-finished", "git")
EXPECTED_RIGHT = ("preview",)


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestShellLayout(unittest.IsolatedAsyncioTestCase):
    async def _app(self, size: tuple[int, int]):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = Store(os.path.join(self.tmp.name, "layout.db"))
        plan = store.add_plan("Plan", "What", goal="Why")
        milestone = store.add_milestone(plan.id, "Milestone", "Details")
        store.add_task(milestone.id, "Task", "Details")
        return create_app(str(store.path)), size

    async def test_wide_shell_puts_four_work_cards_left_and_preview_right(self) -> None:
        app, size = await self._app((130, 40))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            left = app.query_one("#left")
            side = app.query_one("#side")
            self.assertEqual(tuple(child.id for child in left.children), EXPECTED_LEFT)
            self.assertEqual(tuple(child.id for child in side.children), EXPECTED_RIGHT)
            self.assertTrue(side.display)
            self.assertLessEqual(abs(left.size.width - side.size.width), 1)
            active = app.query_one("#plans-active")
            finished = app.query_one("#plans-finished")
            self.assertGreater(active.size.height, finished.size.height)

    async def test_narrow_shell_stacks_the_same_cards_and_hides_the_side(self) -> None:
        app, size = await self._app((90, 40))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            left = app.query_one("#left")
            self.assertEqual(tuple(child.id for child in left.children), EXPECTED_LEFT)
            self.assertFalse(app.query_one("#side").display)
            self.assertFalse(app.query_one("#preview").display)


if __name__ == "__main__":
    unittest.main()
