"""Source trail: grouping commits, files, and PRs without network access."""

import os
import subprocess
import tempfile
import unittest
from unittest import mock

from lazyplan.infrastructure.vcs import CommitStats, DiffRead, FileStat, GitBackend
from lazyplan.services.source import (
    build_source_trail,
    clear_diff_cache,
    clear_stats_cache,
    parse_patch,
    read_commit_stats,
    read_diff,
    read_diff_page,
)
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


class TestDiffParsing(unittest.TestCase):
    PATCH = (
        "diff --git a/a.txt b/a.txt\n"
        "index 111..222 100644\n"
        "--- a/a.txt\n"
        "+++ b/a.txt\n"
        "@@ -1,2 +1,3 @@ section\n"
        " one\n"
        "-two\n"
        "+TWO\n"
        "+three\n"
        "\\ No newline at end of file\n"
        "diff --git a/img.png b/img.png\n"
        "Binary files a/img.png and b/img.png differ\n"
    )

    def test_parse_files_hunks_and_line_numbers(self):
        files = parse_patch(self.PATCH)
        self.assertEqual(len(files), 2)
        first = files[0]
        self.assertEqual(first.path, "a.txt")
        self.assertEqual(first.old_path, "a.txt")
        self.assertFalse(first.binary)
        self.assertEqual(len(first.hunks), 1)
        hunk = first.hunks[0]
        self.assertEqual((hunk.old_start, hunk.old_count), (1, 2))
        self.assertEqual((hunk.new_start, hunk.new_count), (1, 3))
        self.assertEqual(
            [line.kind for line in hunk.lines], ["context", "remove", "add", "add", "meta"]
        )
        self.assertEqual((hunk.lines[0].old_no, hunk.lines[0].new_no), (1, 1))
        self.assertEqual((hunk.lines[1].old_no, hunk.lines[1].new_no), (2, None))
        self.assertEqual((hunk.lines[2].old_no, hunk.lines[2].new_no), (None, 2))
        self.assertEqual((hunk.lines[3].old_no, hunk.lines[3].new_no), (None, 3))
        self.assertEqual(hunk.section, "section")
        self.assertEqual(first.status, "modify")
        self.assertTrue(files[1].binary)

    def test_parse_file_status_and_rename(self):
        patch = (
            "diff --git a/new.txt b/new.txt\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.txt\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
            "diff --git a/old.txt b/old.txt\n"
            "deleted file mode 100644\n"
            "--- a/old.txt\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-gone\n"
            "diff --git a/from.txt b/to.txt\n"
            "similarity index 100%\n"
            "rename from from.txt\n"
            "rename to to.txt\n"
            "diff --git a/empty.txt b/empty.txt\n"
            "new file mode 100644\n"
            "index 0000000..e69de29\n"
        )
        added, deleted, renamed, empty = parse_patch(patch)
        self.assertEqual((added.status, added.old_path, added.new_path), ("add", "", "new.txt"))
        self.assertEqual(
            (deleted.status, deleted.old_path, deleted.new_path),
            ("delete", "old.txt", ""),
        )
        self.assertEqual(
            (renamed.status, renamed.old_path, renamed.new_path),
            ("rename", "from.txt", "to.txt"),
        )
        self.assertEqual(renamed.hunks, ())
        self.assertEqual(empty.status, "add")
        self.assertEqual(empty.hunks, ())

    def test_hunk_section_is_empty_without_context(self):
        patch = "diff --git a/x.txt b/x.txt\n--- a/x.txt\n+++ b/x.txt\n@@ -1 +1 @@\n-a\n+b\n"
        hunk = parse_patch(patch)[0].hunks[0]
        self.assertEqual(hunk.section, "")

    def test_parse_empty_patch(self):
        self.assertEqual(parse_patch(""), ())

    def test_read_diff_cache_and_clear(self):
        class FakeBackend:
            def __init__(self) -> None:
                self.calls = 0

            def diff(self, root, sha, path=""):
                self.calls += 1
                return DiffRead(state="ok", patch=f"{root}:{sha}:{path}")

        backend = FakeBackend()
        clear_diff_cache()
        with mock.patch(
            "lazyplan.services.source_diff.detect_backend", return_value=(backend, "/repo")
        ):
            first = read_diff("/repo", "a" * 40)
            again = read_diff("/repo", "a" * 40)
            scoped = read_diff("/repo", "a" * 40, "a.txt")
        self.assertEqual(backend.calls, 2)
        self.assertIs(first, again)
        self.assertIn("a.txt", scoped.patch)
        clear_diff_cache()
        with mock.patch(
            "lazyplan.services.source_diff.detect_backend", return_value=(backend, "/repo")
        ):
            read_diff("/repo", "a" * 40)
        self.assertEqual(backend.calls, 3)
        clear_diff_cache()

    def test_read_diff_page_slices_whole_files(self):
        class FakeBackend:
            def __init__(self) -> None:
                self.calls = 0

            def diff(self, root, sha, path=""):
                self.calls += 1
                return DiffRead(
                    state="ok",
                    patch=(
                        "diff --git a/a.txt b/a.txt\n"
                        "--- a/a.txt\n"
                        "+++ b/a.txt\n"
                        "@@ -1 +1 @@\n"
                        "-a\n"
                        "+b\n"
                        "diff --git a/b.txt b/b.txt\n"
                        "--- a/b.txt\n"
                        "+++ b/b.txt\n"
                        "@@ -1 +1 @@\n"
                        "-c\n"
                        "+d\n"
                    ),
                )

        backend = FakeBackend()
        clear_diff_cache()
        with mock.patch(
            "lazyplan.services.source_diff.detect_backend", return_value=(backend, "/repo")
        ):
            first = read_diff_page("/repo", "b" * 40, limit=1)
            second = read_diff_page("/repo", "b" * 40, offset=first.next_offset, limit=1)
        self.assertEqual(first.total, 2)
        self.assertTrue(first.has_more)
        self.assertEqual([item.path for item in first.files], ["a.txt"])
        self.assertEqual([item.path for item in second.files], ["b.txt"])
        self.assertFalse(second.has_more)
        self.assertEqual(backend.calls, 1)
        clear_diff_cache()


class TestCommitStats(unittest.TestCase):
    def test_file_stats_joins_name_status_and_numstat(self):
        names = "A\tnew.py\nM\tkeep.py\nD\tgone.py\nR100\told.py\trenamed.py\nM\timage.png\n"
        counts = (
            "3\t0\tnew.py\n"
            "1\t1\tkeep.py\n"
            "0\t2\tgone.py\n"
            "2\t2\told.py => renamed.py\n"
            "-\t-\timage.png\n"
        )
        calls = [
            subprocess.CompletedProcess([], 0, names, ""),
            subprocess.CompletedProcess([], 0, counts, ""),
        ]
        with mock.patch("lazyplan.infrastructure.vcs._run_git", side_effect=calls):
            stats = GitBackend().file_stats("/repo", "a" * 40)
        self.assertEqual(stats.state, "ok")
        self.assertEqual(stats.additions, 6)
        self.assertEqual(stats.deletions, 5)
        by_path = {item.path: item for item in stats.files}
        self.assertEqual(by_path["new.py"].status, "add")
        self.assertEqual((by_path["new.py"].additions, by_path["new.py"].deletions), (3, 0))
        self.assertEqual(by_path["keep.py"].status, "modify")
        self.assertEqual((by_path["keep.py"].additions, by_path["keep.py"].deletions), (1, 1))
        self.assertEqual(by_path["gone.py"].status, "delete")
        self.assertEqual(
            (by_path["renamed.py"].status, by_path["renamed.py"].old_path),
            ("rename", "old.py"),
        )
        self.assertTrue(by_path["image.png"].binary)
        self.assertEqual(
            (by_path["image.png"].additions, by_path["image.png"].deletions),
            (0, 0),
        )

    def test_file_stats_reports_missing_and_error(self):
        with mock.patch(
            "lazyplan.infrastructure.vcs._run_git",
            return_value=subprocess.CompletedProcess([], 1, "", "bad"),
        ):
            missing = GitBackend().file_stats("/repo", "a" * 40)
        self.assertEqual(missing.state, "missing")
        calls = [
            subprocess.CompletedProcess([], 0, "M\ta.py\n", ""),
            subprocess.CompletedProcess([], 1, "", "bad"),
        ]
        with mock.patch("lazyplan.infrastructure.vcs._run_git", side_effect=calls):
            error = GitBackend().file_stats("/repo", "a" * 40)
        self.assertEqual(error.state, "error")

    def test_read_commit_stats_cache_and_clear(self):
        class FakeBackend:
            def __init__(self) -> None:
                self.calls = 0

            def file_stats(self, root, sha):
                self.calls += 1
                return CommitStats(files=(FileStat(path="a.py", status="modify"),))

        backend = FakeBackend()
        clear_stats_cache()
        with mock.patch(
            "lazyplan.services.source_diff.detect_backend", return_value=(backend, "/repo")
        ):
            first = read_commit_stats("/repo", "a" * 40)
            again = read_commit_stats("/repo", "a" * 40)
        self.assertEqual(backend.calls, 1)
        self.assertIs(first, again)
        clear_stats_cache()
        with mock.patch(
            "lazyplan.services.source_diff.detect_backend", return_value=(backend, "/repo")
        ):
            read_commit_stats("/repo", "a" * 40)
        self.assertEqual(backend.calls, 2)
        clear_stats_cache()


@unittest.skipUnless(_git_available(), "git CLI required")
class TestSourceTrail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # The store and git report resolved paths; /var is a symlink on macOS.
        self.repo = os.path.realpath(os.path.join(self.tmp.name, "repo"))
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
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "first"], check=True, timeout=10)
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

    def test_commit_stats_from_checkout(self):
        with open(os.path.join(self.repo, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("a\nb\n")
        with open(os.path.join(self.repo, "b.py"), "w", encoding="utf-8") as fh:
            fh.write("b\n")
        with open(os.path.join(self.repo, "img.bin"), "wb") as fh:
            fh.write(b"\x00\x01\x02")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", self.repo, "commit", "-qm", "second"], check=True, timeout=10)
        sha = subprocess.run(
            ["git", "-C", self.repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()
        clear_stats_cache()
        stats = read_commit_stats(self.repo, sha)
        self.assertEqual(stats.state, "ok")
        by_path = {item.path: item for item in stats.files}
        self.assertEqual(by_path["a.py"].status, "modify")
        self.assertEqual((by_path["a.py"].additions, by_path["a.py"].deletions), (1, 0))
        self.assertEqual(by_path["b.py"].status, "add")
        self.assertTrue(by_path["img.bin"].binary)
        self.assertEqual((stats.additions, stats.deletions), (2, 0))
        clear_stats_cache()

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
