import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services
from lazyplan.store import Store


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
            "task", t.id, sha, subject="fix", author="me", timestamp=7, repo_root="/r"
        )
        self.assertEqual(first.sha, sha)
        self.assertEqual(first.subject, "fix")
        # plan + milestone links work too
        self.store.link_commit("plan", p.id, "a" * 40)
        self.store.link_commit("milestone", s.id, "c" * 40)
        self.assertEqual(len(self.store.list_links("plan", p.id)), 1)
        self.assertEqual(len(self.store.list_links("milestone", s.id)), 1)
        # re-link is idempotent
        again = self.store.link_commit("task", t.id, sha)
        self.assertEqual(again.id, first.id)
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

    def test_export_import_roundtrip_with_links(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.link_commit("plan", p.id, "a" * 40, subject="psub")
        self.store.link_commit("task", t.id, "b" * 40, subject="tsub")
        data = services.export_all(self.store)
        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        counts = services.import_all(s2, data)
        self.assertEqual(counts["links"], 2)
        self.assertEqual(s2.list_links("plan", 1)[0].subject, "psub")
        self.assertEqual(s2.list_links("task", 1)[0].sha, "b" * 40)
        self.assertIn("links", s2.get_full("plan", 1))
        self.assertIn("links", s2.get_full("milestone", 1))
        self.assertIn("links", s2.get_full("task", 1))


if __name__ == "__main__":
    unittest.main()
