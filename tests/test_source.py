"""Source trail: grouping commits, files, and PRs without network access."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.source import build_source_trail
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


@unittest.skipUnless(_git_available(), "git CLI required")
class TestSourceTrail(unittest.TestCase):
    def setUp(self):
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
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "first"], check=True, timeout=10)
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
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.pid, self.sid, self.tid = p.id, s.id, t.id
        self.store.add_repo_link(
            "task",
            self.tid,
            self.repo,
            "git@github.com:org/repo.git",
            branch="main",
            base_sha=self.sha,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_task_trail_groups_commit_files_and_pr(self):
        self.store.link_commit(
            "task",
            self.tid,
            self.sha,
            subject="first",
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
            base_ref="main",
            head_ref="task/7-fix",
            merge_commit_sha="b" * 40,
        )
        trail = build_source_trail(self.store, "task", self.tid)
        self.assertFalse(trail.empty)
        self.assertEqual(trail.commit_count, 1)
        self.assertEqual(trail.file_count, 2)
        self.assertEqual(trail.pull_count, 1)
        self.assertEqual(len(trail.repos), 1)
        repo = trail.repos[0]
        self.assertEqual(repo.branch, "main")
        self.assertFalse(repo.dirty)
        self.assertEqual(repo.pulls[0].number, 7)
        commit = repo.commits[0]
        self.assertEqual(commit.short, self.sha[:12])
        self.assertEqual(commit.owners, (f"T{self.tid} T",))
        self.assertEqual([item.path for item in commit.files], ["a.py", "src/b.py"])
        self.assertTrue(
            all(item.url.startswith("https://github.com/org/repo/blob/") for item in commit.files)
        )
        self.assertEqual(commit.url, f"https://github.com/org/repo/commit/{self.sha}")

    def test_plan_rollup_dedupes_shared_commit_and_pr(self):
        s2 = self.store.add_milestone(self.pid, "S2")
        t2 = self.store.add_task(s2.id, "T2")
        for tid in (self.tid, t2.id):
            self.store.link_commit(
                "task",
                tid,
                self.sha,
                subject="first",
                repo_root=self.repo,
                files=("a.py",),
            )
            self.store.link_forge(
                "task",
                tid,
                7,
                url="https://github.com/org/repo/pull/7",
                title="Fix login",
                state="open",
            )
        trail = build_source_trail(self.store, "plan", self.pid)
        self.assertEqual(trail.commit_count, 1)
        self.assertEqual(trail.pull_count, 1)
        commit = trail.repos[0].commits[0]
        self.assertEqual(commit.owners, (f"T{self.tid} T", f"T{t2.id} T2"))

    def test_empty_trail(self):
        other = self.store.add_task(self.sid, "No source")
        trail = build_source_trail(self.store, "task", other.id)
        self.assertTrue(trail.empty)
        self.assertEqual(trail.commit_count, 0)
        self.assertEqual(trail.pull_count, 0)


if __name__ == "__main__":
    unittest.main()
