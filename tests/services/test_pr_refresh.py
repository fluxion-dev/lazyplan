"""PR refresh: commits to pull requests, checks, and row attribution."""

import os
import subprocess
import tempfile
import unittest

from lazyplan import services
from lazyplan.github import FetchResult
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


class FakeClient:
    def __init__(self, pulls=None, checks=None, reviews=None, branch_pulls=None, merge_pulls=None):
        self.pulls = pulls or []
        self.branch_pulls = branch_pulls or []
        self.merge_pulls = merge_pulls or []
        self.checks_data = checks or {"check_runs": []}
        self.reviews_data = reviews or []
        self.commit_calls = 0
        self.branch_calls = 0
        self.merge_calls = 0

    def pulls_for_commit(self, ref, sha, force=False):
        self.commit_calls += 1
        return FetchResult(data=self.pulls)

    def pulls_for_branch(self, ref, branch, force=False):
        self.branch_calls += 1
        return FetchResult(data=self.branch_pulls)

    def pulls_for_merge(self, ref, sha, force=False):
        self.merge_calls += 1
        return FetchResult(data=self.merge_pulls)

    def checks(self, ref, sha, force=False):
        return FetchResult(data=self.checks_data)

    def reviews(self, ref, number, force=False):
        return FetchResult(data=self.reviews_data)


PR = {
    "number": 7,
    "html_url": "https://github.com/org/repo/pull/7",
    "title": "Fix login",
    "state": "open",
    "merged_at": "2026-10-01T00:00:00Z",
    "merge_commit_sha": "b" * 40,
    "user": {"login": "octocat"},
    "base": {"ref": "main"},
    "head": {"sha": "a" * 40, "ref": "task/7-fix"},
}

CHECKS = {
    "check_runs": [
        {"status": "completed", "conclusion": "success"},
        {"status": "completed", "conclusion": "skipped"},
    ]
}


@unittest.skipUnless(_git_available(), "git CLI required")
class TestPrRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.realpath(os.path.join(self.tmp.name, "repo"))
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.email", "t@t.t"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", self.repo, "config", "user.name", "Tester"],
            check=True,
            timeout=10,
        )
        with open(os.path.join(self.repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "work"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "remote",
                "add",
                "origin",
                "git@github.com:org/repo.git",
            ],
            check=True,
            timeout=10,
        )
        self.sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        self.pid, self.sid = p.id, s.id
        self.tid = self.store.add_task(s.id, "T").id
        self.store.link_commit("task", self.tid, self.sha, subject="work", repo_root=self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_refresh_links_prs_to_the_commit_owner(self):
        client = FakeClient(
            pulls=[PR],
            checks=CHECKS,
            reviews=[{"state": "APPROVED"}, {"state": "COMMENTED"}],
        )
        stats = services.refresh_forge(self.store, "task", self.tid, client=client)
        self.assertEqual(stats["commits"], 1)
        self.assertEqual(stats["linked"], 1)
        self.assertEqual(stats["checks"], 1)
        self.assertEqual(stats["reviews"], 1)
        links = self.store.list_forge_links("task", self.tid)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].number, 7)
        self.assertEqual(links[0].state, "merged")
        self.assertEqual(links[0].checks, "pass")
        self.assertEqual(links[0].reviews, "approved")
        self.assertEqual(links[0].author, "octocat")
        self.assertFalse(links[0].stale)

        # Refreshing the plan attributes the PR to the task that owns the commit.
        services.refresh_forge(self.store, "plan", self.pid, client=client)
        self.assertEqual(self.store.list_forge_links("plan", self.pid), [])
        self.assertEqual(len(self.store.list_forge_links("task", self.tid)), 1)

    def test_refresh_uses_branch_lookup_and_caches_merge_fields(self):
        self.store.add_repo_link(
            "task",
            self.tid,
            self.repo,
            "git@github.com:org/repo.git",
            branch="task/7-fix",
            base_sha=self.sha,
        )
        before = self.store.get_task(self.tid).status
        client = FakeClient(pulls=[], branch_pulls=[PR], merge_pulls=[PR])
        stats = services.refresh_forge(self.store, "task", self.tid, client=client)
        self.assertEqual(stats["branches"], 1)
        self.assertEqual(stats["linked"], 1)
        self.assertEqual(client.branch_calls, 1)
        links = self.store.list_forge_links("task", self.tid)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].state, "merged")
        self.assertEqual(links[0].base_ref, "main")
        self.assertEqual(links[0].head_ref, "task/7-fix")
        self.assertEqual(links[0].merged_at, "2026-10-01T00:00:00Z")
        self.assertEqual(links[0].merge_commit_sha, "b" * 40)
        self.assertEqual(self.store.get_task(self.tid).status, before)
        self.assertEqual(len(self.store.effective_forge_links("plan", self.pid)), 1)

        again = services.refresh_forge(self.store, "task", self.tid, client=client)
        self.assertEqual(again["merges"], 1)
        self.assertEqual(again["linked"], 1)
        self.assertEqual(len(self.store.list_forge_links("task", self.tid)), 1)
        self.assertEqual(self.store.get_task(self.tid).status, before)

    def test_refresh_reports_skipped_non_github_remotes(self):
        subprocess.run(
            [
                "git",
                "-C",
                self.repo,
                "remote",
                "set-url",
                "origin",
                "git@gitlab.com:org/repo.git",
            ],
            check=True,
            timeout=10,
        )
        stats = services.refresh_forge(self.store, "task", self.tid, client=FakeClient(pulls=[PR]))
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["linked"], 0)


if __name__ == "__main__":
    unittest.main()
