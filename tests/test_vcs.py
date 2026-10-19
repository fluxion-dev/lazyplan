import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.vcs import GitBackend, backends, current_head, detect_backend


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


class TestVCS(unittest.TestCase):
    def setUp(self):
        self.backend = GitBackend()

    def test_registry_has_git(self):
        self.assertTrue(any(b.name == "git" for b in backends()))

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
            with open(os.path.join(tmp, "f.txt"), "w") as fh:
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


if __name__ == "__main__":
    unittest.main()
