"""Read-first detail: safe browsing, explicit edit mode, and row actions."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.screens import (
        ConfirmScreen,
        DetailScreen,
        FilterPromptScreen,
        NewMilestoneScreen,
        NewTaskScreen,
    )
except ImportError:  # stdlib-only interpreter: no textual, no screens
    tui_mod = None  # type: ignore[assignment]


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestDetailScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("Plan title", "What we build", goal="Why we build").id
        self.sid = store.add_milestone(self.pid, "Milestone title", "Milestone details").id
        self.tid = store.add_task(self.sid, "Task title", "Task details").id
        store.add_criteria("plan", self.pid, "Criterion one")
        store.add_criteria("plan", self.pid, "Criterion two")
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def _open(self, pilot, kind: str, oid: int) -> None:
        self.app.selected = (kind, oid)
        await pilot.press("enter")
        await pilot.pause()

    async def test_detail_shows_claim_blocked_and_notes(self):
        from textual.widgets import Static

        self.store.claim_task(self.tid, "alice", 300)
        self.store.add_note("task", self.tid, "Use the small parser", actor="alice")
        second = self.store.add_task(self.sid, "Blocked task", "Needs design")
        self.store.set_blocked(second.id, True, "waiting on design", actor="alice")
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn("@alice", body)
            self.assertIn("Use the small parser", body)
            await pilot.press("escape")
            await self._open(pilot, "task", second.id)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn("blocked", body)
            self.assertIn("waiting on design", body)
            self.app.source_filter = "claims"
            claimed = [
                task.id
                for _plan, milestones in self.app._filtered_tree()
                for _milestone, tasks in milestones
                for task in tasks
            ]
            self.assertIn(self.tid, claimed)
            self.assertNotIn(second.id, claimed)

    async def test_read_mode_shows_context_without_inputs(self):
        from textual.widgets import Static

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            screen = self.app.screen
            self.assertIsInstance(screen, DetailScreen)
            body = str(screen.query_one("#detail-body", Static).render())
            self.assertIn("Why we build", body)
            self.assertIn("What we build", body)
            self.assertIn("Criterion one", body)
            self.assertIn("M", body)
            self.assertIn("Milestone title", body)
            self.assertFalse(screen.query_one("#detail-edit").display)
            self.assertTrue(screen.query_one("#detail-read").display)

    @unittest.skipUnless(_git_available(), "git CLI required")
    async def test_detail_shows_git_state_and_commit_url(self):
        from textual.widgets import Static

        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Tester"], check=True, timeout=10)
        with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "detail work"], check=True, timeout=10)
        sha = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", repo, "remote", "add", "origin", "https://github.com/org/repo.git"],
            check=True,
            timeout=10,
        )
        store = Store(self.db)
        store.add_repo_link(
            "task",
            self.tid,
            repo,
            "https://github.com/org/repo.git",
            branch="main",
            base_sha=sha,
        )
        store.link_commit("task", self.tid, sha, subject="detail work", repo_root=repo)
        link = store.list_links("task", self.tid)[0]
        store.update_link(
            link.id,
            subject="detail work",
            author="Tester",
            timestamp=0,
            repo_root=repo,
            stale=True,
            checked_at=1,
        )

        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            preview_lines: list[str] = []
            full = self.store.get_full("task", self.tid)
            assert full is not None
            self.app._preview_common(preview_lines, full)
            preview = "\n".join(preview_lines)
            self.assertIn("git:", preview)
            self.assertIn("main", preview)
            self.assertIn("clean", preview)
            await self._open(pilot, "task", self.tid)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn("git", body)
            self.assertIn("main", body)
            self.assertIn("clean", body)
            self.assertIn("detail work", body)
            self.assertIn("[stale]", body)
            self.assertIn(f"https://github.com/org/repo/commit/{sha}", body)

    async def test_detail_shows_pull_requests(self):
        from textual.widgets import Static

        url = "https://github.com/org/repo/pull/7"
        Store(self.db).link_forge(
            "task",
            self.tid,
            7,
            url=url,
            title="Fix login",
            state="merged",
            checks="pass",
            base_ref="main",
            head_ref="task/7-fix",
            merged_at="2026-10-01T00:00:00Z",
            merge_commit_sha="b" * 40,
        )
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn("pull requests", body)
            self.assertIn("PR #7 merged Fix login", body)
            self.assertIn("checks pass", body)
            self.assertIn("task/7-fix -> main", body)
            self.assertIn(f"merge {'b' * 12}", body)
            self.assertIn(url, body)

    async def test_detail_shows_source_trail_and_opens_screen(self):
        from textual.widgets import Static

        from lazyplan.source_screen import SourceScreen

        repo = os.path.join(self.tmp.name, "source-repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Tester"], check=True, timeout=10)
        with open(os.path.join(repo, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("a\n")
        subprocess.run(["git", "-C", repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "source work"], check=True, timeout=10)
        sha = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        store = Store(self.db)
        store.add_repo_link(
            "task",
            self.tid,
            repo,
            "git@github.com:org/repo.git",
            branch="main",
            base_sha=sha,
        )
        store.link_commit(
            "task",
            self.tid,
            sha,
            subject="source work",
            author="Tester",
            repo_root=repo,
            files=("a.py", "src/b.py"),
        )
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            body = str(self.app.screen.query_one("#detail-body", Static).render())
            self.assertIn("source · 1 commits · 2 files", body)
            self.assertIn("source work", body)
            self.assertIn("g source trail", body)
            await pilot.press("g")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, SourceScreen)

    async def test_detail_rolls_up_pull_requests_for_plan_and_milestone(self):
        from textual.widgets import Static

        Store(self.db).link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="open",
        )
        async with self.app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            for kind, oid in (("milestone", self.sid), ("plan", self.pid)):
                await self._open(pilot, kind, oid)
                body = str(self.app.screen.query_one("#detail-body", Static).render())
                self.assertIn("pull requests", body)
                self.assertIn("PR #7 open Fix login", body)
                self.app.pop_screen()
                await pilot.pause()

    async def test_e_edits_and_saves(self):
        from textual.widgets import Input

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("e")
            await pilot.pause()
            self.assertTrue(self.app.screen.query_one("#detail-edit").display)
            self.app.screen.query_one("#d-title", Input).value = "Plan renamed"
            await pilot.press("ctrl+s")
            await pilot.pause()
            self.assertEqual(Store(self.db).get_plan(self.pid).name, "Plan renamed")
            self.assertFalse(self.app.screen.query_one("#detail-edit").display)

    async def test_dirty_escape_prompts_and_cancel_keeps_detail(self):
        from textual.widgets import Input

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("e")
            await pilot.pause()
            self.app.screen.query_one("#d-title", Input).value = "dirty"
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(Store(self.db).get_task(self.tid).title, "Task title")

    async def test_a_adds_criterion_and_x_ticks(self):
        from textual.widgets import Static

        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            from textual.widgets import Input

            self.app.screen.query_one("#filter-input", Input).value = "Task works"
            await pilot.press("enter")
            await pilot.pause()
            criteria = Store(self.db).list_criteria("task", self.tid)
            self.assertEqual(len(criteria), 1)
            self.assertIn(
                "Task works", str(self.app.screen.query_one("#detail-body", Static).render())
            )
            await pilot.press("x")
            await pilot.pause()
            self.assertTrue(Store(self.db).list_criteria("task", self.tid)[0].done)

    async def test_n_adds_child_by_kind(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, NewMilestoneScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await self._open(pilot, "milestone", self.sid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, NewTaskScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            await self._open(pilot, "task", self.tid)
            await pilot.press("n")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_delete_confirms_cascade_and_cancel_keeps_row(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            text = self.app.screen.text
            self.assertIn("Plan title", text)
            self.assertIn("1 milestones", text)
            self.assertIn("1 tasks", text)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIsNotNone(Store(self.db).get_plan(self.pid))

    async def test_delete_enter_defaults_to_cancel(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            await pilot.press("d")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertIsNotNone(Store(self.db).get_plan(self.pid))

    async def test_detail_fits_80x24(self):
        async with self.app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await self._open(pilot, "plan", self.pid)
            page = self.app.screen.query_one("#detail-page")
            region = page.region
            self.assertLessEqual(region.x + region.width, 80)
            self.assertLessEqual(region.y + region.height, 24)


if __name__ == "__main__":
    unittest.main()
