"""Headless Source screen: grouped tree, preview, filter, open, and copy."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.store import Store

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
        with open(os.path.join(self.repo, "a.py"), "w") as fh:
            fh.write("a\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "source work"], check=True, timeout=10
        )
        self.sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
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

    async def test_empty_state(self):
        empty = self.store.add_task(self.sid, "No source")
        async with self.app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            self.app.push_screen(SourceScreen(self.store, "task", empty.id))
            await pilot.pause()
            tree = self.app.screen.query_one("#source-tree", Tree)
            self.assertIn("No source linked", str(tree.root.children[0].label))
