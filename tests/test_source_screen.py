"""Headless Source screen: grouped tree, preview, filter, open, and copy."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.design import SOURCE_MARKER
from lazyplan.store import Store
from lazyplan.vcs import DiffRead

try:
    from textual.widgets import Input, Tree

    from lazyplan import tui as tui_mod
    from lazyplan.source_screen import SourceScreen
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]
    SourceScreen = None  # type: ignore[assignment]


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


@unittest.skipUnless(
    tui_mod is not None and getattr(tui_mod, "_TEXTUAL_OK", False), "textual not installed"
)
class TestSourceScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "t@t.t"], check=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "Tester"], check=True, timeout=10
        )
        with open(os.path.join(self.repo, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("a\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "source work"], check=True, timeout=10
        )
        self.sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", self.repo, "remote", "add", "origin", "git@github.com:org/repo.git"],
            check=True,
            timeout=10,
        )
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        p = self.store.add_plan("Plan")
        s = self.store.add_milestone(p.id, "Milestone")
        self.pid = p.id
        self.sid = s.id
        self.tid = self.store.add_task(s.id, "Task").id
        self.store.add_repo_link(
            "task",
            self.tid,
            self.repo,
            "git@github.com:org/repo.git",
            branch="main",
            base_sha=self.sha,
        )
        self.store.link_commit(
            "task",
            self.tid,
            self.sha,
            subject="source work",
            author="Tester",
            repo_root=self.repo,
            files=("a.py", "src/b.py"),
        )
        self.store.link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="merged",
            checks="pass",
        )
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _open(self, pilot) -> SourceScreen:
        self.app.push_screen(SourceScreen(self.store, "task", self.tid))
        await pilot.pause()
        return self.app.screen

    async def test_tree_groups_repo_commit_files_and_pr(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            self.assertEqual(len(tree.root.children), 1)
            repo = tree.root.children[0]
            self.assertIn("repo", str(repo.label))
            self.assertEqual(len(repo.children), 2)
            commit = repo.children[0]
            self.assertIn("source work", str(commit.label))
            self.assertEqual(len(commit.children), 2)
            self.assertIn("a.py", str(commit.children[0].label))
            self.assertIn("PR #7", str(repo.children[1].label))
            body = str(screen.query_one("#source-preview-body").render())
            self.assertIn("repo", body)

    async def test_filter_narrows_tree(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            await pilot.press("slash")
            await pilot.pause()
            field = screen.query_one("#source-filter", Input)
            self.assertTrue(field.display)
            field.value = "b.py"
            await pilot.pause()
            tree = screen.query_one("#source-tree", Tree)
            commit = tree.root.children[0].children[0]
            self.assertEqual(len(commit.children), 1)
            self.assertIn("b.py", str(commit.children[0].label))
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(screen.query_one("#source-filter", Input).display)

    async def test_copy_and_open_selected_file(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            file_node = tree.root.children[0].children[0].children[0]
            tree.root.children[0].children[0].expand()
            tree.focus()
            await pilot.pause()
            tree.select_node(file_node)
            await pilot.pause()
            self.assertEqual(tree.cursor_node.data["copy"], "a.py")
            with mock.patch.object(type(screen.app), "copy_to_clipboard") as copied:
                await pilot.press("y")
                await pilot.pause()
                copied.assert_called_once_with("a.py")
            with mock.patch("lazyplan.source_screen.webbrowser.open") as opened:
                await pilot.press("o")
                await pilot.pause()
                opened.assert_called_once()
                self.assertIn("blob", opened.call_args.args[0])

    async def test_plan_source_screen_rolls_up_task_work(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.app.push_screen(SourceScreen(self.store, "plan", self.pid))
            await pilot.pause()
            tree = self.app.screen.query_one("#source-tree", Tree)
            self.assertEqual(len(tree.root.children), 1)
            repo = tree.root.children[0]
            self.assertEqual(len(repo.children), 2)
            self.assertIn("source work", str(repo.children[0].label))

    async def test_stale_commit_is_marked(self):
        link = self.store.list_links("task", self.tid)[0]
        self.store.update_link(
            link.id,
            subject=link.subject,
            author=link.author,
            timestamp=link.timestamp,
            repo_root=link.repo_root,
            stale=True,
            checked_at=1,
            files=link.files,
        )
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            self.assertIn("stale", str(tree.root.children[0].children[0].label))

    async def test_tree_navigation_and_folding_keys(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            repo = tree.root.children[0]
            commit = repo.children[0]
            tree.move_cursor(repo)
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            self.assertIs(tree.cursor_node, commit)
            await pilot.press("k")
            await pilot.pause()
            self.assertIs(tree.cursor_node, repo)
            self.assertTrue(repo.is_expanded)
            await pilot.press("left")
            await pilot.pause()
            self.assertFalse(repo.is_expanded)
            await pilot.press("right")
            await pilot.pause()
            self.assertTrue(repo.is_expanded)
            repo.collapse()
            tree.move_cursor(repo)
            await pilot.pause()
            await pilot.press("left")
            await pilot.pause()
            self.assertIs(tree.cursor_node, tree.root)

    async def test_source_keys_do_not_move_the_main_tree(self):
        from textual.widgets import Tree as TextualTree

        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            main_tree = self.app.query_one("#tree", TextualTree)
            main_plan = self.app._row_nodes[("plan", self.pid)]
            main_cursor = main_tree.cursor_node
            main_expanded = main_plan.is_expanded
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            tree.move_cursor(tree.root.children[0])
            await pilot.pause()
            for key in ("right", "left", "j", "k"):
                await pilot.press(key)
                await pilot.pause()
            self.assertIs(main_tree.cursor_node, main_cursor)
            self.assertEqual(main_plan.is_expanded, main_expanded)

    async def test_main_row_actions_do_not_fire_from_source(self):
        status_before = self.store.get_plan(self.pid).status.value
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            for key in ("d", "s", "e", "n", "g", "f", "F", "A"):
                await pilot.press(key)
                await pilot.pause()
                self.assertIs(self.app.screen, screen, key)
            self.assertEqual(self.store.get_plan(self.pid).status.value, status_before)

    async def test_click_selects_a_source_row(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            clicked = await pilot.click("#source-tree", offset=(10, 1))
            await pilot.pause()
            self.assertTrue(clicked)
            self.assertIsNotNone(tree.cursor_node)
            assert tree.cursor_node is not None
            self.assertEqual(tree.cursor_node.data.get("kind"), "repo")
            body = str(screen.query_one("#source-preview-body").render())
            self.assertIn("repo", body)

    async def test_clicking_a_source_arrow_toggles_the_node(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            repo = tree.root.children[0]
            self.assertTrue(repo.is_expanded)
            clicked = await pilot.click("#source-tree", offset=(4, 1))
            await pilot.pause()
            self.assertTrue(clicked)
            self.assertFalse(repo.is_expanded)
            await pilot.click("#source-tree", offset=(4, 1))
            await pilot.pause()
            self.assertTrue(repo.is_expanded)
            root = tree.root
            self.assertTrue(root.is_expanded)
            await pilot.click("#source-tree", offset=(0, 0))
            await pilot.pause()
            self.assertFalse(root.is_expanded)
            await pilot.click("#source-tree", offset=(0, 0))
            await pilot.pause()
            self.assertTrue(root.is_expanded)

    async def test_commit_and_file_previews_render_diff(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            commit_node = repo_node.children[0]
            tree.select_node(commit_node)
            await pilot.pause()
            body = str(screen.query_one("#source-preview-body").render())
            self.assertIn("root commit", body)
            self.assertIn("+a", body)
            block = screen._diff_block(self.repo, self.sha)
            self.assertTrue(any("[green]" in row for row in block))
            self.assertTrue(any("   1" in row for row in block))

            commit_node.expand()
            tree.select_node(commit_node.children[0])
            await pilot.pause()
            file_body = str(screen.query_one("#source-preview-body").render())
            self.assertIn("a.py", file_body)
            self.assertIn("+a", file_body)

    async def test_large_diff_is_capped_with_remainder(self):
        with open(os.path.join(self.repo, "big.txt"), "w", encoding="utf-8") as fh:
            fh.write("".join(f"line {i}\n" for i in range(20)))
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "big change"], check=True, timeout=10
        )
        big = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            with mock.patch("lazyplan.source_screen.DIFF_PREVIEW_LINES", 3):
                block = screen._diff_block(self.repo, big)
            self.assertTrue(any("more lines" in row for row in block))

    async def test_diff_states_are_explicit(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            for state, detail, needle in (
                ("binary", "binary file", "binary"),
                ("merge", "merge commit", "merge commit"),
                ("empty", "no textual changes", "no textual changes"),
                ("missing", "commit not found", "not found"),
                ("error", "diff unavailable", "unavailable"),
            ):
                with mock.patch(
                    "lazyplan.source_screen.read_diff",
                    return_value=DiffRead(state=state, detail=detail),
                ):
                    block = screen._diff_block(self.repo, self.sha)
                self.assertTrue(any(needle in row.lower() for row in block), state)

    async def test_source_rows_carry_marker(self):
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            screen = await self._open(pilot)
            tree = screen.query_one("#source-tree", Tree)
            repo_node = tree.root.children[0]
            commit_node = repo_node.children[0]
            pull_node = repo_node.children[1]
            for node in (repo_node, commit_node, commit_node.children[0], pull_node):
                self.assertIn(SOURCE_MARKER, str(node.label))
            empty = self.store.add_task(self.sid, "No source")
            self.app.push_screen(SourceScreen(self.store, "task", empty.id))
            await pilot.pause()
            empty_tree = self.app.screen.query_one("#source-tree", Tree)
            self.assertNotIn(SOURCE_MARKER, str(empty_tree.root.children[0].label))

    async def test_empty_state(self):
        empty = self.store.add_task(self.sid, "No source")
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.app.push_screen(SourceScreen(self.store, "task", empty.id))
            await pilot.pause()
            tree = self.app.screen.query_one("#source-tree", Tree)
            self.assertIn("No source linked", str(tree.root.children[0].label))
