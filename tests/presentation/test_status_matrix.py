"""Cross-surface emoji matrix: every state on every in-scope surface."""

from __future__ import annotations

import os
import random
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import Status, Task
from lazyplan.presentation.shared import design
from lazyplan.store import Store

try:
    from rich.cells import cell_len
    from rich.text import Text
    from textual.widgets import Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    CriteriaHub = None  # type: ignore[assignment]
    Text = cell_len = Tree = None  # type: ignore[assignment,misc]


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestStatusMatrix(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "matrix.db"))
        self.plan = self.store.add_plan("Matrix plan", worktree_required=False)
        self.milestone = self.store.add_milestone(self.plan.id, "Matrix slice")
        self.todo = self.store.add_task(self.milestone.id, "Todo work")
        self.doing = self.store.add_task(self.milestone.id, "Doing work")
        self.store.set_status_raw("task", self.doing.id, Status.DOING)
        self.blocked = self.store.add_task(self.milestone.id, "Blocked work")
        self.store.set_blocked(self.blocked.id, True, "waiting", actor="test")
        self.done = self.store.add_task(self.milestone.id, "Done work")
        self.store.set_status_raw("task", self.done.id, Status.DONE)
        self.done_plan = self.store.add_plan("Reviewed plan", worktree_required=False)
        self.done_milestone = self.store.add_milestone(self.done_plan.id, "Finished slice")
        done_t = self.store.add_task(self.done_milestone.id, "Finished work")
        services.set_status(self.store, "task", done_t.id, Status.DONE, actor="test")
        self.done_task = done_t

    def row(self, app: object, key: tuple[str, int]) -> str:
        return Text.from_markup(app._row_labels[key]).plain  # type: ignore[attr-defined]

    async def open_tree(self, app: object, pilot: object) -> None:
        app._expanded.update(  # type: ignore[attr-defined]
            {
                ("plan", self.plan.id),
                ("milestone", self.milestone.id),
                ("plan", self.done_plan.id),
                ("milestone", self.done_milestone.id),
            }
        )
        app.refresh_all()  # type: ignore[attr-defined]
        await pilot.pause()  # type: ignore[attr-defined]

    def assert_no_state_words(self, text: str) -> None:
        for word in ("doing", "blocked", "review"):
            self.assertNotIn(f" {word}", text)

    async def test_tree_matrix_wide_and_narrow(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await self.open_tree(app, pilot)

            expected = {
                ("task", self.todo.id): "📝",
                ("task", self.doing.id): "🔨",
                ("task", self.blocked.id): "🚧",
                ("task", self.done.id): "✅",
                ("plan", self.plan.id): "🔍",  # blocked work rolls review up
            }
            for key, mark in expected.items():
                with self.subTest(key=key, width="wide"):
                    self.assertTrue(self.row(app, key).endswith(mark))
                    self.assert_no_state_words(self.row(app, key))

            app._apply_layout(design.EMOJI_MIN_WIDTH - 1)  # type: ignore[attr-defined]
            app.refresh_all()  # type: ignore[attr-defined]
            await pilot.pause()

            fallback = {
                ("task", self.todo.id): "○",
                ("task", self.doing.id): "◐",
                ("task", self.blocked.id): "!",
                ("task", self.done.id): "●",
                ("plan", self.plan.id): "?",
            }
            for key, mark in fallback.items():
                with self.subTest(key=key, width="narrow"):
                    self.assertTrue(self.row(app, key).endswith(mark))
                    for emoji in ("📝", "🔨", "🔍", "🚧", "✅"):
                        self.assertNotIn(emoji, self.row(app, key))

    async def test_plan_review_panel_reads_review_and_done_tasks_read_done(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await self.open_tree(app, pilot)
            plan_key = ("plan", self.done_plan.id)
            task_key = ("task", self.done_task.id)
            self.assertTrue(self.row(app, plan_key).endswith("🔍"))
            self.assertTrue(self.row(app, task_key).endswith("✅"))
            self.assert_no_state_words(self.row(app, plan_key))

            app._apply_layout(40)  # type: ignore[attr-defined]
            app.refresh_all()  # type: ignore[attr-defined]
            await pilot.pause()
            self.assertTrue(self.row(app, plan_key).endswith("?"))
            self.assertTrue(self.row(app, task_key).endswith("●"))

    async def test_agents_card_matrix_wide_and_narrow(self) -> None:
        services.start_claim(self.store, self.doing.id, "claude")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.6)
            body = str(app.query_one("#agents-body").render())
            self.assertIn("🔨 @claude", body)

            app._apply_layout(40)  # type: ignore[attr-defined]
            app.update_agents()  # type: ignore[attr-defined]
            await pilot.pause()
            body = str(app.query_one("#agents-body").render())
            self.assertIn("◐ @claude", body)
            self.assertNotIn("🔨", body)

    async def test_hub_status_rows_matrix_wide_and_narrow(self) -> None:
        done = self.store.add_criteria("plan", self.plan.id, "Finished criterion", actor="test")
        self.store.update_criterion(done.id, done=True, actor="test")
        self.store.add_criteria("plan", self.plan.id, "Open criterion", actor="test")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            hub = CriteriaHub(self.store, "plan", self.plan.id)
            app.push_screen(hub)
            await pilot.pause()
            labels = [entry.label for entry in hub.entries]
            self.assertTrue(any(label.startswith("✅ C") for label in labels))
            self.assertTrue(any(label.startswith("📝 C") for label in labels))

            app._apply_layout(40)  # type: ignore[attr-defined]
            hub.on_resize()
            await pilot.pause()
            labels = [entry.label for entry in hub.entries]
            self.assertTrue(any(label.startswith("● C") for label in labels))
            self.assertTrue(any(label.startswith("○ C") for label in labels))
            for label in labels:
                for emoji in ("📝", "🔨", "🔍", "🚧", "✅"):
                    self.assertNotIn(emoji, label)

    async def test_status_line_matrix_wide_and_narrow(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await self.open_tree(app, pilot)
            app.select_row("task", self.doing.id)  # type: ignore[attr-defined]
            await pilot.pause()
            head = str(app.query_one("#preview-head").render())
            self.assertIn("🔨", head)
            self.assertNotIn("doing", head)

            app.select_row("milestone", self.milestone.id)  # type: ignore[attr-defined]
            await pilot.pause()
            body = app.query_one("#preview-body").source or ""
            self.assertIn(f"T{self.blocked.id}  Blocked work · 🚧", body)

            app._apply_layout(40)  # type: ignore[attr-defined]
            app.update_preview(force=True)  # type: ignore[attr-defined]
            await pilot.pause()
            body = app.query_one("#preview-body").source or ""
            self.assertIn(f"T{self.blocked.id}  Blocked work · !", body)

            app.select_row("task", self.doing.id)  # type: ignore[attr-defined]
            app.update_preview(force=True)  # type: ignore[attr-defined]
            await pilot.pause()
            head = str(app.query_one("#preview-head").render())
            self.assertIn("◐", head)

    async def test_row_labels_are_stable_when_order_is_shuffled(self) -> None:
        states = [
            Task(id=1, milestone_id=1, title="One", status=Status.TODO),
            Task(id=2, milestone_id=1, title="Two", status=Status.DOING),
            Task(id=3, milestone_id=1, title="Three", status=Status.TODO, blocked=True),
            Task(id=4, milestone_id=1, title="Four", status=Status.DONE),
        ]
        expected = {1: "📝", 2: "🔨", 3: "🚧", 4: "✅"}
        order = list(states)
        random.Random(28).shuffle(order)
        for task in order:
            row = Text.from_markup(design.task_row(task, width=80)).plain
            self.assertTrue(row.endswith(expected[task.id]))
            self.assert_no_state_words(row)

    async def test_no_row_clips_cells_at_any_width(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await self.open_tree(app, pilot)
            tree = app.query_one("#tree", Tree)
            for key, depth in (
                (("plan", self.plan.id), 3),
                (("milestone", self.milestone.id), 7),
                (("task", self.todo.id), 11),
            ):
                with self.subTest(key=key):
                    plain = self.row(app, key)
                    width = app.tree_controller.row_width(tree, depth)  # type: ignore[attr-defined]
                    self.assertEqual(cell_len(plain), width)


if __name__ == "__main__":
    unittest.main()
