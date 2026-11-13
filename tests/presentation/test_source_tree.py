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


@unittest.skipUnless(create_app is not None, "textual not installed")
class SourceTreeStatsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.store = Store(os.path.join(self.tmp.name, "plan.db"))
        plan = self.store.add_plan("Stats")
        milestone = self.store.add_milestone(plan.id, "Slice")
        self.milestone = milestone
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
        stats = CommitStats(
            files=(
                FileStat(path="app/a.py", status="modify", additions=3, deletions=1),
                FileStat(path="app/b.py", status="add", additions=5),
            )
        )
        with mock.patch(
            "lazyplan.presentation.tui.screens.source.read_commit_stats",
            return_value=stats,
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
                self.assertIn("+8 -1", str(commit_node.label))
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
                self.assertEqual(app.screen._view.page_offset, 300)
                app.screen.action_less()
                await pilot.pause()
                self.assertIn("page one", str(body.content))
                self.assertEqual(app.screen._view.page_offset, 0)

    async def test_style_toggles_pass_options_to_the_renderer(self) -> None:
        with mock.patch(
            "lazyplan.presentation.tui.screens.source.render_diff_preview",
            return_value=DiffPreview(rows=("x",), total=1),
        ) as reader:
            app = create_app(str(self.store.path))
            async with app.run_test(size=(170, 40)) as pilot:
                app.push_screen(SourceScreen(self.store, "task", self.task.id))
                await pilot.pause(0.5)
                tree = app.screen.query_one("#source-tree", Tree)
                repo_node = tree.root.children[0]
                repo_node.expand()
                tree.move_cursor(repo_node.children[0])
                await pilot.pause()
                app.screen.action_toggle_wrap()
                await pilot.pause()
                self.assertFalse(app.screen._view.wrap)
                self.assertFalse(reader.call_args.kwargs["wrap"])
                app.screen.action_toggle_fold()
                await pilot.pause()
                self.assertFalse(app.screen._view.fold)
                self.assertFalse(reader.call_args.kwargs["fold"])
                app.screen.action_toggle_split()
                await pilot.pause()
                self.assertTrue(app.screen._view.split)
                self.assertTrue(reader.call_args.kwargs["split"])

    async def test_split_refuses_a_narrow_pane(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(50, 20)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.5)
            tree = app.screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            repo_node.expand()
            tree.move_cursor(repo_node.children[0])
            await pilot.pause()
            app.screen.action_toggle_split()
            await pilot.pause()
            self.assertFalse(app.screen._view.split)

    async def test_empty_trail_shows_guidance(self) -> None:
        empty = self.store.add_task(self.milestone.id, "No source")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", empty.id))
            await pilot.pause(0.4)
            tree = app.screen.query_one("#source-tree", Tree)
            self.assertIn("No source linked", str(tree.root.children[0].label))

    async def test_filter_narrows_the_tree_and_reports_no_match(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.5)
            tree = app.screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            repo_node.expand()
            app.screen._filter = "app/a.py"
            app.screen._build_tree()
            await pilot.pause()
            labels = self._tree_labels(tree.root)
            self.assertTrue(any("app/a.py" in label for label in labels))
            self.assertFalse(any("app/b.py" in label for label in labels))
            app.screen._filter = "nothing-here"
            app.screen._build_tree()
            await pilot.pause()
            labels = self._tree_labels(tree.root)
            self.assertTrue(any("No source matches" in label for label in labels))

    async def test_copy_open_and_owner_use_the_selected_row(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.5)
            tree = app.screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            repo_node.expand()
            tree.move_cursor(repo_node.children[0])
            await pilot.pause()
            with (
                mock.patch.object(app, "copy_to_clipboard") as copy,
                mock.patch("lazyplan.presentation.tui.screens.source.webbrowser.open") as open_url,
                mock.patch.object(app, "select_row") as select_row,
            ):
                app.screen.action_copy()
                copy.assert_called_once_with(SHA)
                app.screen.action_open()
                open_url.assert_called_once()
                app.screen.action_open_owner()
                select_row.assert_called_once_with("task", self.task.id)

    async def test_refresh_drops_preview_caches(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause(0.5)
            tree = app.screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            repo_node.expand()
            tree.move_cursor(repo_node.children[0])
            await pilot.pause()
            self.assertTrue(app.screen._diff_cache)
            with mock.patch.object(app.screen, "_load"):
                app.screen.action_refresh()
            self.assertFalse(app.screen._diff_cache)
            self.assertFalse(app.screen._stats_loaded)
            self.assertFalse(app.screen._commit_nodes)

    @staticmethod
    def _tree_labels(node: object) -> list[str]:
        out = [str(node.label)]  # type: ignore[attr-defined]
        for child in node.children:  # type: ignore[attr-defined]
            out.extend(SourceTreeStatsTest._tree_labels(child))
        return out


if __name__ == "__main__":
    unittest.main()
