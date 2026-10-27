import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.vcs import (
    GitBackend,
    backends,
    commit_url,
    current_head,
    detect_backend,
    file_url,
    web_remote,
)


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, encoding="utf-8", timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def _configure(repo: str) -> None:
    """Set a deterministic identity for commits in a temp repo."""
    subprocess.run(
        ["git", "-C", repo, "config", "user.email", "t@t.t"],
        check=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", repo, "config", "user.name", "Tester"],
        check=True,
        timeout=10,
    )


def _init_repo(repo: str) -> None:
    """Create a repo with a deterministic main branch and identity."""
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, timeout=10)
    _configure(repo)


def _commit(repo: str, name: str, body: str, subject: str) -> None:
    """Write one file and commit it."""
    with open(os.path.join(repo, name), "w", encoding="utf-8") as fh:
        fh.write(body)
    subprocess.run(["git", "-C", repo, "add", "."], check=True, timeout=10)
    subprocess.run(
        ["git", "-C", repo, "commit", "-qm", subject],
        check=True,
        timeout=10,
    )


class TestVCS(unittest.TestCase):
    def setUp(self):
        self.backend = GitBackend()

    def test_registry_has_git(self):
        self.assertTrue(any(b.name == "git" for b in backends()))

    def test_remote_and_commit_urls(self):
        self.assertEqual(web_remote("git@github.com:org/repo.git"), "https://github.com/org/repo")
        self.assertEqual(
            web_remote("https://github.com/org/repo.git"), "https://github.com/org/repo"
        )
        self.assertEqual(
            web_remote("ssh://git@github.com/org/repo.git"), "https://github.com/org/repo"
        )
        self.assertEqual(web_remote("/local/path"), "")
        sha = "a" * 40
        self.assertEqual(
            commit_url("git@github.com:org/repo.git", sha),
            f"https://github.com/org/repo/commit/{sha}",
        )
        self.assertEqual(commit_url("", sha), "")
        self.assertEqual(
            file_url("git@github.com:org/repo.git", sha, "src/my file.py"),
            f"https://github.com/org/repo/blob/{sha}/src/my%20file.py",
        )
        self.assertEqual(file_url("", sha, "src/a.py"), "")
        self.assertEqual(file_url("git@github.com:org/repo.git", sha, ""), "")

    def test_non_repo_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.backend.detect(tmp))
            self.assertFalse(self.backend.is_available(tmp))
            backend, root = detect_backend(tmp)
            self.assertIsNone(backend)
            self.assertIsNone(root)
            be, info = current_head(tmp)
            self.assertIsNone(be)
            self.assertIsNone(info)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_git_repo_head_and_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True, timeout=10)
            subprocess.run(
                ["git", "-C", tmp, "config", "user.email", "t@t.t"],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "-C", tmp, "config", "user.name", "Tester"],
                check=True,
                timeout=10,
            )
            with open(os.path.join(tmp, "f.txt"), "w", encoding="utf-8") as fh:
                fh.write("hi\n")
            subprocess.run(["git", "-C", tmp, "add", "."], check=True, timeout=10)
            subprocess.run(
                ["git", "-C", tmp, "commit", "-qm", "first commit"],
                check=True,
                timeout=10,
            )
            root = self.backend.detect(tmp)
            self.assertIsNotNone(root)
            self.assertTrue(self.backend.is_available(tmp))
            sha = self.backend.head(tmp)
            self.assertIsNotNone(sha)
            assert sha is not None
            self.assertEqual(len(sha), 40)
            info = self.backend.show(tmp, sha)
            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.sha, sha)
            self.assertEqual(info.subject, "first commit")
            self.assertEqual(info.author, "Tester")
            # short sha resolves to the same commit
            short = self.backend.show(tmp, sha[:7])
            self.assertIsNotNone(short)
            assert short is not None
            self.assertEqual(short.sha, sha)
            # unknown sha -> None
            self.assertIsNone(self.backend.show(tmp, "0" * 40))
            # current_head helper works from a subdir
            sub = os.path.join(tmp, "sub")
            os.makedirs(sub)
            be, cur = current_head(sub)
            self.assertIsNotNone(be)
            self.assertIsNotNone(cur)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_empty_repo_has_no_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", tmp], check=True, timeout=10)
            # repo exists so detect passes, but no commits -> head None
            self.assertIsNotNone(self.backend.detect(tmp))
            self.assertIsNone(self.backend.head(tmp))

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_status_uses_one_git_call(self):
        import lazyplan.vcs as vcs_mod

        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "f.txt", "hi\n", "first")
            with mock.patch("lazyplan.vcs._run_git", wraps=vcs_mod._run_git) as run:
                status = self.backend.status(tmp)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(status.branch, "main")
            self.assertFalse(status.dirty)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_branch_status_and_remotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "f.txt", "hi\n", "first")
            status = self.backend.status(tmp)
            self.assertEqual(status.branch, "main")
            self.assertEqual(status.head, self.backend.head(tmp))
            self.assertFalse(status.dirty)
            self.assertFalse(status.detached)
            self.assertEqual(status.ahead, 0)
            self.assertEqual(status.behind, 0)

            with open(os.path.join(tmp, "new.txt"), "w", encoding="utf-8") as fh:
                fh.write("dirty\n")
            self.assertTrue(self.backend.status(tmp).dirty)

            self.assertEqual(self.backend.remotes(tmp), [])
            url = "https://github.com/org/repo.git"
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "origin", url],
                check=True,
                timeout=10,
            )
            scp = "git@github.com:org/repo.git"
            subprocess.run(
                ["git", "-C", tmp, "remote", "add", "upstream", scp],
                check=True,
                timeout=10,
            )
            remotes = self.backend.remotes(tmp)
            self.assertEqual([r.name for r in remotes], ["origin", "upstream"])
            self.assertEqual(remotes[0].fetch_url, url)
            self.assertEqual(remotes[0].push_url, url)
            self.assertEqual(remotes[1].fetch_url, scp)
            self.assertEqual(remotes[1].push_url, scp)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_log_range_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "f.txt", "one\n", "first")
            base = self.backend.head(tmp)
            assert base is not None
            _commit(tmp, "f.txt", "two\n", "second")
            _commit(tmp, "f.txt", "three\n", "third")

            ranged = self.backend.log(tmp, f"{base}..HEAD")
            self.assertEqual([c.subject for c in ranged], ["third", "second"])
            limited = self.backend.log(tmp, limit=1)
            self.assertEqual([c.subject for c in limited], ["third"])
            self.assertEqual(self.backend.log(tmp, "does-not-exist..HEAD"), [])

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_detached_head_has_no_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "f.txt", "hi\n", "first")
            subprocess.run(
                ["git", "-C", tmp, "checkout", "-q", "--detach"],
                check=True,
                timeout=10,
            )
            self.assertIsNone(self.backend.branch(tmp))
            status = self.backend.status(tmp)
            self.assertEqual(status.branch, "")
            self.assertTrue(status.detached)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_commit_metadata_includes_body_files_parents_and_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "first.txt", "one\n", "first")
            first = self.backend.head(tmp)
            assert first is not None
            with open(os.path.join(tmp, "second.txt"), "w", encoding="utf-8") as fh:
                fh.write("two\n")
            subprocess.run(
                ["git", "-C", tmp, "add", "."],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "-C", tmp, "commit", "-qm", "second\n\nbody line"],
                check=True,
                timeout=10,
            )
            head = self.backend.head(tmp)
            assert head is not None
            info = self.backend.show(tmp, head)
            assert info is not None
            self.assertEqual(info.subject, "second")
            self.assertEqual(info.body, "body line")
            self.assertEqual(info.files, ("second.txt",))
            self.assertEqual(info.parents, (first,))
            self.assertEqual(info.branch, "main")

            root = self.backend.show(tmp, first)
            assert root is not None
            self.assertEqual(root.files, ("first.txt",))
            self.assertEqual(root.parents, ())

            logged = self.backend.log(tmp)
            self.assertEqual(logged[0].body, "body line")
            self.assertEqual(logged[0].parents, (first,))
            self.assertEqual(logged[0].files, ())

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_diff_reads_commit_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "a.txt", "one\ntwo\n", "first")
            _commit(tmp, "b.txt", "bee\n", "second")
            sha = self.backend.head(tmp)
            assert sha is not None
            read = self.backend.diff(tmp, sha)
            self.assertEqual(read.state, "ok")
            self.assertIn("+bee", read.patch)
            self.assertFalse(read.truncated)
            scoped = self.backend.diff(tmp, sha, "b.txt")
            self.assertEqual(scoped.state, "ok")
            self.assertIn("b.txt", scoped.patch)
            self.assertNotIn("a.txt", scoped.patch)
            self.assertEqual(self.backend.diff(tmp, "0" * 40).state, "missing")
            self.assertEqual(self.backend.diff(tmp, "").state, "missing")

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_diff_marks_root_merge_and_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "a.txt", "one\n", "root")
            root = self.backend.head(tmp)
            assert root is not None
            read = self.backend.diff(tmp, root)
            self.assertEqual(read.state, "root")
            self.assertIn("+one", read.patch)

            subprocess.run(["git", "-C", tmp, "checkout", "-qb", "side"], check=True, timeout=10)
            _commit(tmp, "side.txt", "side\n", "side work")
            subprocess.run(["git", "-C", tmp, "checkout", "-q", "main"], check=True, timeout=10)
            _commit(tmp, "main.txt", "main\n", "main work")
            subprocess.run(
                ["git", "-C", tmp, "merge", "-q", "--no-ff", "-m", "merge side", "side"],
                check=True,
                timeout=10,
            )
            merge = self.backend.head(tmp)
            assert merge is not None
            self.assertEqual(self.backend.diff(tmp, merge).state, "merge")

            with open(os.path.join(tmp, "blob.bin"), "wb") as fh:
                fh.write(b"\x00\x01\x02")
            subprocess.run(["git", "-C", tmp, "add", "."], check=True, timeout=10)
            subprocess.run(["git", "-C", tmp, "commit", "-qm", "binary"], check=True, timeout=10)
            binary = self.backend.head(tmp)
            assert binary is not None
            self.assertEqual(self.backend.diff(tmp, binary).state, "binary")

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_diff_caps_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            body = "".join(f"line {i}\n" for i in range(20))
            _commit(tmp, "a.txt", body, "many lines")
            sha = self.backend.head(tmp)
            assert sha is not None
            with mock.patch("lazyplan.vcs.DIFF_MAX_LINES", 3):
                read = self.backend.diff(tmp, sha)
            self.assertTrue(read.truncated)
            self.assertLessEqual(len(read.patch.splitlines()), 3)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_diff_uses_only_read_only_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            _init_repo(tmp)
            _commit(tmp, "a.txt", "one\n", "first")
            sha = self.backend.head(tmp)
            assert sha is not None
            calls: list[list[str]] = []
            real_run = subprocess.run

            def record(*args, **kwargs):
                calls.append(list(args[0]))
                return real_run(*args, **kwargs)

            with mock.patch("lazyplan.vcs.subprocess.run", side_effect=record):
                self.backend.diff(tmp, sha)
            verbs = {call[3] for call in calls}
            self.assertLessEqual(verbs, {"rev-parse", "rev-list", "show"})

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_ahead_and_behind_with_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = os.path.join(tmp, "remote.git")
            seed = os.path.join(tmp, "seed")
            ahead = os.path.join(tmp, "ahead")
            behind = os.path.join(tmp, "behind")
            subprocess.run(
                ["git", "init", "-q", "--bare", "-b", "main", bare],
                check=True,
                timeout=10,
            )
            _init_repo(seed)
            _commit(seed, "f.txt", "one\n", "first")
            subprocess.run(
                ["git", "-C", seed, "remote", "add", "origin", bare],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "-C", seed, "push", "-q", "-u", "origin", "main"],
                check=True,
                timeout=10,
            )
            for clone in (ahead, behind):
                subprocess.run(
                    ["git", "clone", "-q", bare, clone],
                    check=True,
                    timeout=10,
                )
                _configure(clone)

            _commit(behind, "other.txt", "other\n", "remote change")
            subprocess.run(
                ["git", "-C", behind, "push", "-q"],
                check=True,
                timeout=10,
            )
            subprocess.run(
                ["git", "-C", ahead, "fetch", "-q"],
                check=True,
                timeout=10,
            )
            _commit(ahead, "local.txt", "local\n", "local change")

            status = self.backend.status(ahead)
            self.assertEqual(status.upstream, "origin/main")
            self.assertEqual(status.ahead, 1)
            self.assertEqual(status.behind, 1)


if __name__ == "__main__":
    unittest.main()
