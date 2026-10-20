import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main as lpui_main
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


def _run(argv):
    buf = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        rc = lpui_main(argv)
    return rc, buf.getvalue(), err.getvalue()


@unittest.skipUnless(_git_available(), "git CLI required")
class TestVcsCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        subprocess.run(["git", "init", "-q", self.repo], check=True, timeout=10)
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
        with open(os.path.join(self.repo, "f.txt"), "w") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", self.repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", self.repo, "commit", "-qm", "cli commit"],
            check=True,
            timeout=10,
        )
        self.plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(self.plain)
        self.db = os.path.join(self.tmp.name, "t.db")
        store = Store(self.db)
        p = store.add_plan("P")
        s = store.add_milestone(p.id, "S")
        store.add_task(s.id, "T")
        self.old_cwd = os.getcwd()

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_link_commits_show_roundtrip(self):
        os.chdir(self.repo)
        rc, out, _ = _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("cli commit", out)
        rc, out, _ = _run(["--db", self.db, "show", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("commits:", out)
        self.assertIn("cli commit", out)
        # explicit sha + unlink
        store = Store(self.db)
        sha = store.list_links("task", 1)[0].sha
        rc, _, _ = _run(["--db", self.db, "link", "--kind", "task", "--id", "1", "--sha", sha])
        self.assertEqual(rc, 0)  # idempotent
        rc, _, _ = _run(["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", sha])
        self.assertEqual(rc, 0)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("(no commits linked)", out)

    def test_status_done_auto_captures(self):
        os.chdir(self.repo)
        rc, _, _ = _run(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"])
        self.assertEqual(rc, 0)
        store = Store(self.db)
        links = store.list_links("task", 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(len(links[0].sha), 40)
        # second done is a no-op dedupe
        rc, _, _ = _run(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(Store(self.db).list_links("task", 1)), 1)

    def test_unknown_sha_and_missing_link(self):
        os.chdir(self.repo)
        rc, _, err = _run(
            ["--db", self.db, "link", "--kind", "task", "--id", "1", "--sha", "0" * 40]
        )
        self.assertEqual(rc, 2)
        self.assertIn("unknown commit", err)
        rc, _, _ = _run(
            ["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", "0" * 40]
        )
        self.assertEqual(rc, 1)

    def test_outside_git_disabled(self):
        os.chdir(self.plain)
        rc, _, err = _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 2)
        self.assertIn("no VCS backend", err)
        rc, _, err = _run(
            ["--db", self.db, "unlink", "--kind", "task", "--id", "1", "--sha", "a" * 40]
        )
        self.assertEqual(rc, 2)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1"])
        self.assertEqual(rc, 0)
        self.assertIn("(no commits linked)", out)
        rc, out, _ = _run(["--db", self.db, "commits", "--kind", "task", "--id", "1", "--json"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "[]")

    def test_list_json_includes_links(self):
        os.chdir(self.repo)
        _run(["--db", self.db, "link", "--kind", "task", "--id", "1"])
        rc, out, _ = _run(["--db", self.db, "list", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("links", out)


if __name__ == "__main__":
    unittest.main()
