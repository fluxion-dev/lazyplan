"""Responsive status marks: emoji on wide terminals, glyphs when narrow or ASCII."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from rich.cells import cell_len
    from rich.text import Text
    from textual.widgets import Tree

    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    Text = cell_len = Tree = None  # type: ignore[assignment,misc]


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestStatusFallback(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "fallback.db"))
        self.plan = self.store.add_plan("Fallback plan", worktree_required=False)
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Working task")
        self.store.set_status_raw("task", self.task.id, Status.DOING)

    def row(self, app: object, key: tuple[str, int]) -> str:
        return Text.from_markup(app._row_labels[key]).plain  # type: ignore[attr-defined]

    def row_cells(self, app: object, key: tuple[str, int], depth: int) -> tuple[int, int]:
        tree = app.query_one("#tree", Tree)  # type: ignore[attr-defined]
        width = app.tree_controller.row_width(tree, depth)  # type: ignore[attr-defined]
        return cell_len(self.row(app, key)), width

    async def expand(self, app: object, pilot: object) -> None:
        app._expanded.update(  # type: ignore[attr-defined]
            {("plan", self.plan.id), ("milestone", self.milestone.id)}
        )
        app.refresh_all()  # type: ignore[attr-defined]
        await pilot.pause()  # type: ignore[attr-defined]

    async def test_a_narrow_terminal_switches_to_single_cell_glyphs(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self.expand(app, pilot)
            key = ("task", self.task.id)
            self.assertTrue(self.row(app, key).startswith("🔨 "))

            app._apply_layout(79)  # type: ignore[attr-defined]
            app.refresh_all()  # type: ignore[attr-defined]
            await pilot.pause()

            plain = self.row(app, key)
            self.assertTrue(plain.startswith("◐ "))
            self.assertNotIn("🔨", plain)
            cells, width = self.row_cells(app, key, 11)
            self.assertEqual(cells, width)

    async def test_widening_the_terminal_restores_emoji(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await self.expand(app, pilot)
            key = ("task", self.task.id)

            app._apply_layout(40)  # type: ignore[attr-defined]
            app.refresh_all()  # type: ignore[attr-defined]
            await pilot.pause()
            self.assertTrue(self.row(app, key).startswith("◐ "))

            app._apply_layout(120)  # type: ignore[attr-defined]
            app.refresh_all()  # type: ignore[attr-defined]
            await pilot.pause()
            self.assertTrue(self.row(app, key).startswith("🔨 "))

    async def test_an_ascii_terminal_never_gets_emoji(self) -> None:
        with mock.patch.dict(os.environ, {"TERM": "dumb"}):
            app = create_app(str(self.store.path))
            async with app.run_test(size=(160, 40)) as pilot:
                await pilot.pause()
                await self.expand(app, pilot)
                self.assertFalse(app.state.emoji)
                plain = self.row(app, ("task", self.task.id))
                self.assertTrue(plain.startswith("◐ "))
                for emoji in ("📝", "🔨", "🔍", "🚧", "✅"):
                    self.assertNotIn(emoji, plain)

    async def test_the_wide_tree_keeps_its_exact_row_width(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            await self.expand(app, pilot)
            for key, depth in (
                (("plan", self.plan.id), 3),
                (("milestone", self.milestone.id), 7),
                (("task", self.task.id), 11),
            ):
                with self.subTest(key=key):
                    cells, width = self.row_cells(app, key, depth)
                    self.assertEqual(cells, width)


if __name__ == "__main__":
    unittest.main()
