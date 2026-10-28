import os
import sqlite3
import subprocess
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store


def _git_available() -> bool:
    try:
        out = subprocess.run(["git", "--version"], capture_output=True, encoding="utf-8", timeout=5)
    except (FileNotFoundError, OSError):
        return False
    return out.returncode == 0


class TestVcsLinks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_list_unlink_idempotent(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        sha = "b" * 40
        first = self.store.link_commit(
            "task",
            t.id,
            sha,
            subject="fix",
            author="me",
            timestamp=7,
            repo_root="/r",
            files=("src/a.py", "tests/test_a.py"),
        )
        self.assertEqual(first.sha, sha)
        self.assertEqual(first.subject, "fix")
        self.assertEqual(first.files, ("src/a.py", "tests/test_a.py"))
        # plan + milestone links work too
        self.store.link_commit("plan", p.id, "a" * 40)
        self.store.link_commit("milestone", s.id, "c" * 40)
        self.assertEqual(len(self.store.list_links("plan", p.id)), 1)
        self.assertEqual(len(self.store.list_links("milestone", s.id)), 1)
        # re-link is idempotent and preserves metadata when not supplied
        again = self.store.link_commit("task", t.id, sha)
        self.assertEqual(again.id, first.id)
        self.assertEqual(again.files, ("src/a.py", "tests/test_a.py"))
        self.assertEqual(len(self.store.list_links("task", t.id)), 1)
        # unlink + missing unlink
        self.assertTrue(self.store.unlink_commit("task", t.id, sha))
        self.assertEqual(self.store.list_links("task", t.id), [])
        self.assertFalse(self.store.unlink_commit("task", t.id, sha))

    def test_link_validation(self):
        p = self.store.add_plan("P")
        with self.assertRaises(KeyError):
            self.store.link_commit("task", 999, "a" * 40)
        with self.assertRaises(ValueError):
            self.store.link_commit("plan", p.id, "short")
        with self.assertRaises(ValueError):
            self.store.link_commit("nope", p.id, "a" * 40)
        with self.assertRaises(ValueError):
            self.store.list_links("nope", p.id)
        with self.assertRaises(ValueError):
            self.store.unlink_commit("nope", p.id, "a" * 40)

    def test_cascade_on_delete(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.link_commit("plan", p.id, "a" * 40)
        self.store.link_commit("milestone", s.id, "b" * 40)
        self.store.link_commit("task", t.id, "c" * 40)
        self.assertTrue(self.store.delete("milestone", s.id))
        self.assertEqual(self.store.list_links("milestone", s.id), [])
        self.assertEqual(self.store.list_links("task", t.id), [])
        # plan link survives milestone delete
        self.assertEqual(len(self.store.list_links("plan", p.id)), 1)
        self.assertTrue(self.store.delete("plan", p.id))
        self.assertEqual(self.store.list_links("plan", p.id), [])

    def test_effective_links_roll_up_and_dedupe(self):
        p = self.store.add_plan("P")
        s1 = self.store.add_milestone(p.id, "S1")
        s2 = self.store.add_milestone(p.id, "S2")
        t1 = self.store.add_task(s1.id, "T1")
        t2 = self.store.add_task(s2.id, "T2")
        self.store.link_commit("plan", p.id, "a" * 40)
        self.store.link_commit("milestone", s1.id, "b" * 40)
        self.store.link_commit("task", t1.id, "c" * 40)
        self.store.link_commit("task", t2.id, "c" * 40)
        self.store.link_commit("task", t2.id, "d" * 40)

        plan_shas = [link.sha for link in self.store.effective_links("plan", p.id)]
        self.assertEqual(plan_shas, ["a" * 40, "b" * 40, "c" * 40, "d" * 40])
        self.assertEqual(
            [link.sha for link in self.store.effective_links("milestone", s1.id)],
            ["b" * 40, "c" * 40],
        )
        self.assertEqual(
            [link.sha for link in self.store.effective_links("task", t2.id)],
            ["c" * 40, "d" * 40],
        )
        full = self.store.get_full("plan", p.id)
        self.assertEqual(len(full["effective_links"]), 4)

    def test_migration_adds_refresh_columns(self):
        legacy = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.execute(
            "CREATE TABLE vcs_links ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "parent_kind TEXT NOT NULL,"
            "parent_id INTEGER NOT NULL,"
            "sha TEXT NOT NULL,"
            "subject TEXT NOT NULL DEFAULT '',"
            "author TEXT NOT NULL DEFAULT '',"
            "timestamp INTEGER NOT NULL DEFAULT 0,"
            "repo_root TEXT NOT NULL DEFAULT '',"
            "UNIQUE(parent_kind, parent_id, sha))"
        )
        conn.execute(
            "INSERT INTO vcs_links (parent_kind, parent_id, sha) VALUES ('task', 1, ?)",
            ("a" * 40,),
        )
        conn.commit()
        conn.close()

        store = Store(legacy)
        links = store.list_links("task", 1)
        self.assertEqual(len(links), 1)
        self.assertFalse(links[0].stale)
        self.assertEqual(links[0].checked_at, 0)
        self.assertEqual(links[0].files, ())
        # Migration is idempotent.
        Store(legacy)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_refresh_updates_metadata_and_marks_missing(self):
        repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Tester"], check=True, timeout=10)
        with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", repo, "add", "."], check=True, timeout=10)
        subprocess.run(
            ["git", "-C", repo, "commit", "-qm", "real subject"],
            check=True,
            timeout=10,
        )
        sha = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()

        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.link_commit("task", t.id, sha, subject="wrong", author="nobody", repo_root=repo)
        fake = "0" * 40
        self.store.link_commit("task", t.id, fake, subject="ghost", repo_root=repo)

        result = services.refresh_links(self.store, "task", t.id)
        self.assertEqual(result, {"checked": 2, "updated": 1, "stale": 1})
        links = {link.sha: link for link in self.store.list_links("task", t.id)}
        self.assertEqual(links[sha].subject, "real subject")
        self.assertEqual(links[sha].author, "Tester")
        self.assertEqual(links[sha].files, ("f.txt",))
        self.assertFalse(links[sha].stale)
        self.assertTrue(links[fake].stale)
        self.assertGreater(links[fake].checked_at, 0)

    @unittest.skipUnless(_git_available(), "git CLI required")
    def test_refresh_marks_rewritten_commit_stale(self):
        repo = os.path.join(self.tmp.name, "rewritten")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t.t"], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Tester"], check=True, timeout=10)
        with open(os.path.join(repo, "f.txt"), "w", encoding="utf-8") as fh:
            fh.write("hi\n")
        subprocess.run(["git", "-C", repo, "add", "."], check=True, timeout=10)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "old subject"], check=True, timeout=10)
        old = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=True,
        ).stdout.strip()

        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.link_commit("task", t.id, old, subject="old subject", repo_root=repo)

        subprocess.run(
            ["git", "-C", repo, "commit", "--amend", "-qm", "new subject"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", repo, "reflog", "expire", "--expire=now", "--all"],
            check=True,
            timeout=10,
        )
        subprocess.run(
            ["git", "-C", repo, "gc", "--prune=now", "--quiet"],
            check=True,
            timeout=10,
        )

        result = services.refresh_links(self.store, "task", t.id)
        self.assertEqual(result, {"checked": 1, "updated": 0, "stale": 1})
        link = self.store.list_links("task", t.id)[0]
        self.assertTrue(link.stale)
        self.assertEqual(link.subject, "old subject")

    def test_repo_link_branch_and_base_roundtrip(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        first = self.store.add_repo_link(
            "task", t.id, "/checkout", "https://example.test/r", "task/1-one", "a" * 40
        )
        self.assertEqual(first["branch"], "task/1-one")
        self.assertEqual(first["base_sha"], "a" * 40)

        again = self.store.add_repo_link(
            "task", t.id, "/checkout", "https://example.test/r", "task/2-two", "b" * 40
        )
        self.assertEqual(again["id"], first["id"])
        self.assertEqual(again["branch"], "task/2-two")
        self.assertEqual(again["base_sha"], "b" * 40)
        self.assertEqual(len(self.store.list_repos("task", t.id)), 1)

        data = services.export_all(self.store)
        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        services.import_all(s2, data)
        repos = s2.list_repos("task", 1)
        self.assertEqual(repos[0]["branch"], "task/2-two")
        self.assertEqual(repos[0]["base_sha"], "b" * 40)

    def test_export_import_roundtrip_with_links(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.link_commit("plan", p.id, "a" * 40, subject="psub")
        self.store.link_commit("task", t.id, "b" * 40, subject="tsub", files=("src/x.py",))
        data = services.export_all(self.store)
        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        counts = services.import_all(s2, data)
        self.assertEqual(counts["links"], 2)
        self.assertEqual(s2.list_links("plan", 1)[0].subject, "psub")
        self.assertEqual(s2.list_links("task", 1)[0].sha, "b" * 40)
        self.assertEqual(s2.list_links("task", 1)[0].files, ("src/x.py",))
        self.assertIn("links", s2.get_full("plan", 1))
        self.assertIn("links", s2.get_full("milestone", 1))
        self.assertIn("links", s2.get_full("task", 1))


if __name__ == "__main__":
    unittest.main()
