"""Forge link persistence: PRs/issues, cache, cascade, and export."""

import os
import sqlite3
import tempfile
import unittest

from lazyplan import services
from lazyplan.render import render_full
from lazyplan.store import Store


class TestForgeStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        self.pid = p.id
        self.sid = s.id
        self.tid = self.store.add_task(s.id, "T").id

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_list_update_and_unlink(self):
        link = self.store.link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="open",
            checks="pending",
            reviews="changes",
            author="octocat",
            base_ref="main",
            head_ref="task/7-fix",
            merged_at="2026-10-01T00:00:00Z",
            merge_commit_sha="b" * 40,
            updated_at=10,
            stale=True,
            payload='{"number": 7}',
        )
        self.assertEqual(link.number, 7)
        self.assertEqual(link.state, "open")
        self.assertEqual(link.reviews, "changes")
        self.assertEqual(link.base_ref, "main")
        self.assertEqual(link.head_ref, "task/7-fix")
        self.assertEqual(link.merge_commit_sha, "b" * 40)
        self.assertTrue(link.stale)
        again = self.store.link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="merged",
            checks="pass",
            author="octocat",
            updated_at=20,
            payload='{"number": 7, "merged": true}',
        )
        self.assertEqual(again.id, link.id)
        self.assertEqual(again.state, "merged")
        self.assertEqual(again.checks, "pass")
        self.assertEqual(len(self.store.list_forge_links("task", self.tid)), 1)

        self.store.link_forge("task", self.tid, 3, kind="issue", title="Bug")
        pulls = self.store.list_forge_links("task", self.tid, kind="pull")
        self.assertEqual([item.number for item in pulls], [7])
        self.assertEqual(len(self.store.list_forge_links("task", self.tid)), 2)

        self.assertTrue(self.store.unlink_forge("task", self.tid, 7))
        self.assertFalse(self.store.unlink_forge("task", self.tid, 7))

    def test_validation(self):
        with self.assertRaises(KeyError):
            self.store.link_forge("task", 999, 1)
        with self.assertRaises(ValueError):
            self.store.link_forge("task", self.tid, 0)
        with self.assertRaises(ValueError):
            self.store.link_forge("nope", self.tid, 1)

    def test_cascade_on_delete(self):
        self.store.link_forge("plan", self.pid, 1)
        self.store.link_forge("milestone", self.sid, 2)
        self.store.link_forge("task", self.tid, 3)
        self.assertTrue(self.store.delete("milestone", self.sid))
        self.assertEqual(self.store.list_forge_links("milestone", self.sid), [])
        self.assertEqual(self.store.list_forge_links("task", self.tid), [])
        self.assertEqual(len(self.store.list_forge_links("plan", self.pid)), 1)
        self.assertTrue(self.store.delete("plan", self.pid))
        self.assertEqual(self.store.list_forge_links("plan", self.pid), [])

    def test_cache_put_and_get(self):
        self.assertIsNone(self.store.cache_get("pulls:org/repo"))
        self.store.cache_put("pulls:org/repo", 'W/"one"', 100, '{"items": []}')
        cached = self.store.cache_get("pulls:org/repo")
        assert cached is not None
        self.assertEqual(cached["etag"], 'W/"one"')
        self.assertEqual(cached["fetched_at"], 100)
        self.store.cache_put("pulls:org/repo", 'W/"two"', 200, '{"items": [1]}')
        cached = self.store.cache_get("pulls:org/repo")
        assert cached is not None
        self.assertEqual(cached["etag"], 'W/"two"')
        self.assertEqual(cached["payload"], '{"items": [1]}')

    def test_export_import_roundtrip(self):
        self.store.link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="merged",
            checks="pass",
            reviews="approved",
            author="octocat",
            base_ref="main",
            head_ref="task/7-fix",
            merged_at="2026-10-01T00:00:00Z",
            merge_commit_sha="b" * 40,
            updated_at=20,
            stale=True,
            payload='{"number": 7}',
        )
        data = services.export_all(self.store)
        db2 = os.path.join(self.tmp.name, "imported.db")
        other = Store(db2)
        counts = services.import_all(other, data)
        self.assertEqual(counts["forge_links"], 1)
        links = other.list_forge_links("task", 1)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].state, "merged")
        self.assertEqual(links[0].title, "Fix login")
        self.assertEqual(links[0].reviews, "approved")
        self.assertEqual(links[0].base_ref, "main")
        self.assertEqual(links[0].head_ref, "task/7-fix")
        self.assertEqual(links[0].merged_at, "2026-10-01T00:00:00Z")
        self.assertEqual(links[0].merge_commit_sha, "b" * 40)
        self.assertTrue(links[0].stale)
        self.assertEqual(links[0].payload, '{"number": 7}')

    def test_get_full_includes_forge_links(self):
        self.store.link_forge("task", self.tid, 7, title="Fix login")
        full = self.store.get_full("task", self.tid)
        assert full is not None
        self.assertEqual(len(full["forge_links"]), 1)
        self.assertEqual(full["forge_links"][0]["number"], 7)
        plan = self.store.get_full("plan", self.pid)
        assert plan is not None
        self.assertEqual(len(plan["effective_forge_links"]), 1)
        self.assertEqual(plan["effective_forge_links"][0]["number"], 7)

    def test_feed_logs_link_and_state_changes(self):
        self.store.link_forge("task", self.tid, 7, state="open")
        feed = self.store.feed(10)
        self.assertTrue(any(row["kind"] == "forge" and row["action"] == "link" for row in feed))
        self.store.link_forge("task", self.tid, 7, state="merged")
        feed = self.store.feed(10)
        self.assertTrue(any(row["kind"] == "forge" and row["action"] == "state" for row in feed))
        before = len(self.store.feed(50))
        self.store.link_forge("task", self.tid, 7, state="merged")
        self.assertEqual(len(self.store.feed(50)), before)

    def test_show_renders_cached_pr_without_network(self):
        self.store.link_forge(
            "task",
            self.tid,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="merged",
            checks="pass",
            reviews="approved",
            base_ref="main",
            head_ref="task/7-fix",
            merged_at="2026-10-01T00:00:00Z",
            merge_commit_sha="b" * 40,
            stale=True,
        )
        full = self.store.get_full("plan", self.pid)
        assert full is not None
        text = render_full("plan", full)
        self.assertIn("pull requests:", text)
        self.assertIn("PR #7 merged Fix login", text)
        self.assertIn("checks pass", text)
        self.assertIn("reviews approved", text)
        self.assertIn("task/7-fix -> main", text)
        self.assertIn(f"merge {'b' * 12}", text)
        self.assertIn("[stale]", text)

    def test_migration_adds_merge_fields_to_existing_forge_links(self):
        for col in ("base_ref", "head_ref", "merged_at", "merge_commit_sha"):
            conn = sqlite3.connect(self.db)
            conn.execute(f"ALTER TABLE forge_links DROP COLUMN {col}")
            conn.commit()
            conn.close()
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()
        migrated = Store(self.db)
        link = migrated.link_forge(
            "task",
            self.tid,
            7,
            base_ref="main",
            head_ref="task/7-fix",
            merged_at="2026-10-01T00:00:00Z",
            merge_commit_sha="b" * 40,
        )
        self.assertEqual(link.base_ref, "main")
        self.assertEqual(link.head_ref, "task/7-fix")
        self.assertEqual(link.merge_commit_sha, "b" * 40)

    def test_migration_creates_forge_tables(self):
        legacy = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.execute(
            "CREATE TABLE plans (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',"
            " status TEXT NOT NULL DEFAULT 'todo', goal TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "CREATE TABLE milestones (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " plan_id INTEGER NOT NULL, title TEXT NOT NULL,"
            " description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo')"
        )
        conn.execute(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " milestone_id INTEGER NOT NULL, title TEXT NOT NULL,"
            " status TEXT NOT NULL DEFAULT 'todo', description TEXT NOT NULL DEFAULT '')"
        )
        conn.commit()
        conn.close()

        store = Store(legacy)
        p = store.add_plan("P")
        s = store.add_milestone(p.id, "S")
        t = store.add_task(s.id, "T")
        store.link_forge("task", t.id, 1, title="PR", reviews="approved", stale=True)
        links = store.list_forge_links("task", t.id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].reviews, "approved")
        self.assertTrue(links[0].stale)
        store.cache_put("k", "e", 1, "{}")
        self.assertIsNotNone(store.cache_get("k"))


if __name__ == "__main__":
    unittest.main()
