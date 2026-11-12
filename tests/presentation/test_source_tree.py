"""Expanding a commit loads file stats once and paints them on the rows."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

try:
    from textual.widgets import Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.source import SourceScreen
    from lazyplan.presentation.tui.views.source import DiffPreview
    from lazyplan.services.source import CommitStats, FileStat
    from lazyplan.store import Store
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SourceScreen = Tree = None  # type: ignore[assignment]
    CommitStats = FileStat = Store = DiffPreview = None  # type: ignore[assignment]

SHA = "a" * 40
STATS = CommitStats(
    files=(
        FileStat(path="app/a.py", status="modify", additions=3, deletions=1),
        FileStat(path="app/b.py", status="add", additions=5),
    )
)


@unittest.skipUnless(create_app is not None, "textual not installed")
class SourceTreeStatsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.store = Store(os.path.join(self.tmp.name, "plan.db"))
        plan = self.store.add_plan("Stats")
        milestone = self.store.add_milestone(plan.id, "Slice")
        self.task = self.store.add_task(milestone.id, "Read diffs")
        self.store.add_repo_link(
            "task",
            self.task.id,
            self.repo,
            "git@github.com:org/repo.git",
        )
        self.store.link_commit(
            "task",
            self.task.id,
            SHA,
            subject="Render diffs",
            author="Tester",
            repo_root=self.repo,
            files=("app/a.py", "app/b.py"),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def _labels(self, app: object, node: object) -> list[str]:
        return [str(child.label) for child in node.children]  # type: ignore[attr-defined]

    async def test_commit_expand_loads_stats_once(self) -> None:
        with mock.patch(
            "lazyplan.presentation.tui.screens.source.read_commit_stats",
            return_value=STATS,
        ) as reader:
            app = create_app(str(self.store.path))
            async with app.run_test(size=(130, 35)) as pilot:
                app.push_screen(SourceScreen(self.store, "task", self.task.id))
                await pilot.pause(0.5)
                tree = app.screen.query_one("#source-tree", Tree)
                repo_node = tree.root.children[0]
                repo_node.expand()
                commit_node = repo_node.children[0]
                commit_node.expand()
                for _ in range(40):
                    labels = await self._labels(app, commit_node)
                    if any("M app/a.py" in label for label in labels):
                        break
                    await pilot.pause(0.05)
                labels = await self._labels(app, commit_node)
                self.assertTrue(any("M app/a.py" in label and "+3" in label for label in labels))
                self.assertTrue(any("A app/b.py" in label and "+5" in label for label in labels))
                self.assertIn("2 files", str(commit_node.label))
                self.assertEqual(reader.call_count, 1)
                commit_node.collapse()
                commit_node.expand()
                await pilot.pause(0.2)
                self.assertEqual(reader.call_count, 1)

    async def test_commit_preview_indexes_files_and_n_p_walks(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.5)
            tree = app.screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            repo_node.expand()
            commit_node = repo_node.children[0]
            tree.move_cursor(commit_node)
            await pilot.pause()
            body = app.screen.query_one("#source-preview-body")
            text = str(body.content)
            self.assertIn("files 1/2", text)
            self.assertIn("app/a.py", text)
            app.screen.action_next_file()
            await pilot.pause()
            app.screen.action_next_file()
            await pilot.pause()
            text = str(body.content)
            self.assertIn("file 2/2", text)
            self.assertIn("app/b.py", text)
            app.screen.action_prev_file()
            await pilot.pause()
            self.assertIn("file 1/2", str(body.content))

    async def test_more_and_less_page_a_cached_preview(self) -> None:
        page_one = DiffPreview(rows=("page one",), total=600, has_more=True)
        page_two = DiffPreview(rows=("page two",), offset=300, total=600)
        with mock.patch(
            "lazyplan.presentation.tui.screens.source.render_diff_preview",
            side_effect=[page_one, page_two],
        ):
            app = create_app(str(self.store.path))
            async with app.run_test(size=(130, 35)) as pilot:
                app.push_screen(SourceScreen(self.store, "task", self.task.id))
                await pilot.pause(0.5)
                tree = app.screen.query_one("#source-tree", Tree)
                repo_node = tree.root.children[0]
                repo_node.expand()
                commit_node = repo_node.children[0]
                tree.move_cursor(commit_node)
                await pilot.pause()
                body = app.screen.query_one("#source-preview-body")
                self.assertIn("page one", str(body.content))
                app.screen.action_more()
                await pilot.pause()
                self.assertIn("page two", str(body.content))
                self.assertEqual(app.screen._page_offset, 300)
                app.screen.action_less()
                await pilot.pause()
                self.assertIn("page one", str(body.content))
                self.assertEqual(app.screen._page_offset, 0)


if __name__ == "__main__":
    unittest.main()
