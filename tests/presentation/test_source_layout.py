"""The source screen stacks on narrow terminals and splits on wide ones."""

from __future__ import annotations

import os
import tempfile
import unittest

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.source import SourceScreen
    from lazyplan.store import Store
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SourceScreen = None  # type: ignore[assignment]
    Store = None  # type: ignore[assignment]


@unittest.skipUnless(create_app is not None, "textual not installed")
class SourceLayoutTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "plan.db"))
        plan = self.store.add_plan("Layout")
        milestone = self.store.add_milestone(plan.id, "Slice")
        self.task = self.store.add_task(milestone.id, "Read diffs")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_stacks_below_one_hundred_columns(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.3)
            tree = app.screen.query_one("#source-tree-wrap")
            preview = app.screen.query_one("#source-preview")
            self.assertEqual(tree.region.x, preview.region.x)
            self.assertLess(tree.region.y, preview.region.y)
            self.assertGreaterEqual(tree.region.height, 6)
            self.assertGreaterEqual(preview.region.height, 8)

    async def test_sits_side_by_side_at_one_thirty(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.3)
            tree = app.screen.query_one("#source-tree-wrap")
            preview = app.screen.query_one("#source-preview")
            self.assertEqual(tree.region.y, preview.region.y)
            self.assertLess(tree.region.x, preview.region.x)
            self.assertGreater(preview.region.width, tree.region.width)


if __name__ == "__main__":
    unittest.main()
