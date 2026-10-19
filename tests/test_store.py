import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hierarchy(self):
        p = self.store.add_project("Site", goal="why", priority="p1")
        s = self.store.add_story(p.id, "Home", priority="p0")
        t = self.store.add_task(s.id, "Hero", description="do it", priority="p0")
        self.assertEqual(self.store.counts()["tasks"], 1)
        tree = self.store.tree()
        self.assertEqual(tree[0][0].id, p.id)
        self.assertEqual(tree[0][1][0][1][0].id, t.id)
        self.assertTrue(self.store.set_status("task", t.id, Status.DONE))
        self.assertEqual(self.store.counts()["tasks_done"], 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.store.add_project("   ")
        with self.assertRaises(ValueError):
            self.store.add_project("P", priority="p9")
        with self.assertRaises(KeyError):
            self.store.add_story(999, "nope")
        with self.assertRaises(KeyError):
            self.store.add_task(999, "nope")

    def test_cli_json_ingress(self):
        rc = lpui_main(["--db", self.db, "--json", "add-project", "--title", "P1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-story", "--project", "1", "--title", "S1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-task", "--story", "1", "--title", "T1"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.counts()["tasks"], 1)

    def test_project_why_what_priority(self):
        p = self.store.add_project("P", description="the what", goal="the why", priority="p1")
        self.assertEqual(self.store.get_project(p.id).goal, "the why")
        self.assertEqual(self.store.get_project(p.id).priority, "p1")
        upd = self.store.update_project(p.id, goal="why v2", priority="p0")
        assert upd is not None
        self.assertEqual(upd.goal, "why v2")
        self.assertEqual(upd.priority, "p0")
        cleared = self.store.update_project(p.id, priority="")
        assert cleared is not None
        self.assertEqual(cleared.priority, "")

    def test_priority_sort(self):
        p = self.store.add_project("P")
        self.store.add_story(p.id, "Low", priority="p2")
        self.store.add_story(p.id, "High", priority="p0")
        self.assertEqual([s.title for s in self.store.list_stories(p.id)], ["High", "Low"])
        with self.assertRaises(ValueError):
            self.store.add_story(p.id, "Bad", priority="p9")
        with self.assertRaises(ValueError):
            self.store.add_task(1, "Bad", priority="p9")

    def test_criteria_on_project_story_task(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        for kind, oid in (("project", p.id), ("story", s.id), ("task", t.id)):
            c1 = self.store.add_criteria(kind, oid, "works")
            c2 = self.store.add_criteria(kind, oid, "fast")
            self.assertEqual(self.store.criteria_progress(kind, oid), (0, 2))
            self.store.set_criteria(c1.id, True)
            self.assertEqual(self.store.criteria_progress(kind, oid), (1, 2))
            self.assertEqual(len(self.store.open_criteria(kind, oid)), 1)
            self.assertTrue(self.store.delete_criteria(c2.id))
        with self.assertRaises(KeyError):
            self.store.add_criteria("task", 999, "x")
        with self.assertRaises(KeyError):
            self.store.add_criteria("project", 999, "x")
        with self.assertRaises(ValueError):
            self.store.add_criteria("nope", 1, "x")

    def test_criteria_cascade_on_delete(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.add_criteria("project", p.id, "pc")
        self.store.add_criteria("story", s.id, "sc")
        self.store.add_criteria("task", t.id, "tc")
        self.assertTrue(self.store.delete("project", p.id))
        self.assertEqual(self.store.list_criteria("project", p.id), [])
        self.assertEqual(self.store.list_criteria("story", s.id), [])
        self.assertEqual(self.store.list_criteria("task", t.id), [])

    def test_migration_from_old_db(self):
        import sqlite3

        legacy = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
            goal TEXT NOT NULL DEFAULT '', success_metrics TEXT NOT NULL DEFAULT '',
            scope_in TEXT NOT NULL DEFAULT '', scope_out TEXT NOT NULL DEFAULT '',
            assumptions TEXT NOT NULL DEFAULT '');
        CREATE TABLE stories (id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo', start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '',
            estimate TEXT NOT NULL DEFAULT '', blocked_by TEXT NOT NULL DEFAULT '');
        CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
            estimate TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
            owner TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '', blocked_by TEXT NOT NULL DEFAULT '');
        CREATE TABLE criteria (id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_kind TEXT NOT NULL CHECK (parent_kind IN ('story', 'task')),
            parent_id INTEGER NOT NULL,
            text TEXT NOT NULL CHECK (trim(text) <> ''),
            done INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            actor TEXT NOT NULL DEFAULT 'human', kind TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '');
        INSERT INTO projects (name, goal) VALUES ('Old', 'old-why');
        INSERT INTO stories (project_id, title, priority) VALUES (1, 'OldS', 'p0');
        INSERT INTO tasks (story_id, title) VALUES (1, 'OldT');
        INSERT INTO criteria (parent_kind, parent_id, text) VALUES ('story', 1, 'old-crit');
        """)
        conn.commit()
        conn.close()
        s = Store(legacy)  # must migrate, not crash
        self.assertEqual(s.get_project(1).name, "Old")
        self.assertEqual(s.get_project(1).goal, "old-why")
        self.assertEqual(s.get_project(1).priority, "")
        self.assertEqual(s.get_task(1).description, "")
        self.assertEqual(s.list_criteria("story", 1)[0].text, "old-crit")
        # project-level criteria now allowed on the migrated table
        c = s.add_criteria("project", 1, "new-crit")
        self.assertEqual(c.text, "new-crit")
        self.assertEqual(s.counts()["tasks"], 1)

    def test_export_import_roundtrip(self):
        p = self.store.add_project("P", goal="g", priority="p1")
        self.store.set_status("project", p.id, Status.DOING)
        s = self.store.add_story(p.id, "S", priority="p1")
        self.store.add_criteria("project", p.id, "pcrit")
        t = self.store.add_task(s.id, "T", description="d")
        self.store.set_status("task", t.id, Status.DONE)
        self.store.add_criteria("task", t.id, "works")
        data = self.store.export_all()
        import tempfile

        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        counts = s2.import_all(data)
        self.assertEqual(counts, {"projects": 1, "stories": 1, "tasks": 1, "criteria": 2})
        self.assertEqual(s2.get_project(1).status, Status.DONE)  # rolled up: only story done
        self.assertEqual(s2.get_story(1).status, Status.DONE)  # rolled up: its task is done
        self.assertEqual(s2.get_project(1).goal, "g")
        self.assertEqual(s2.get_project(1).priority, "p1")
        self.assertEqual(s2.get_task(1).description, "d")
        self.assertEqual(s2.get_task(1).status, Status.DONE)
        self.assertEqual(s2.criteria_progress("project", 1), (0, 1))
        self.assertEqual(s2.criteria_progress("task", 1), (0, 1))
        with self.assertRaises(ValueError):
            s2.import_all({"nope": True})

    def test_cli_planning_surface(self):
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-project",
                    "--title",
                    "P1",
                    "--why",
                    "w",
                    "--what",
                    "x",
                    "--priority",
                    "p1",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-story",
                    "--project",
                    "1",
                    "--title",
                    "S1",
                    "--priority",
                    "p0",
                    "--desc",
                    "d",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "add-task", "--story", "1", "--title", "T1", "--priority", "p1"]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "list", "--priority", "p0"]), 0)
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-criteria",
                    "--kind",
                    "project",
                    "--id",
                    "1",
                    "--text",
                    "works",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "criteria", "--kind", "project", "--id", "1"]), 0
        )
        self.assertEqual(lpui_main(["--db", self.db, "check", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "uncheck", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "export", "--format", "markdown"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"]), 0
        )  # warns, proceeds
        self.assertEqual(lpui_main(["--db", self.db, "delete-criteria", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "update",
                    "--kind",
                    "project",
                    "--id",
                    "1",
                    "--why",
                    "w2",
                    "--priority",
                    "none",
                ]
            ),
            0,
        )
        self.assertEqual(self.store.get_project(1).priority, "")

    def test_cli_show(self):
        self.assertEqual(
            lpui_main(["--db", self.db, "add-project", "--title", "P1", "--why", "g1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-story", "--project", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "add-task", "--story", "1", "--title", "T1", "--desc", "d1"]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "show", "--kind", "project", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "show", "--kind", "story", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "update", "--kind", "task", "--id", "1", "--desc", "d2"]),
            0,
        )
        self.assertEqual(self.store.get_task(1).description, "d2")

    def test_events_and_fingerprint(self):
        fp0 = self.store.fingerprint()
        p = self.store.add_project("P", actor="agent-1")
        fp1 = self.store.fingerprint()
        self.assertNotEqual(fp0, fp1)
        events = self.store.feed(5)
        self.assertTrue(any(e["actor"] == "agent-1" and e["kind"] == "project" for e in events))
        s = self.store.add_story(p.id, "S", actor="agent-1")
        t = self.store.add_task(s.id, "T", actor="agent-1")
        self.assertEqual(self.store.cycle_status("task", t.id, actor="agent-1"), Status.DOING)
        self.assertEqual(self.store.cycle_status("task", t.id, actor="agent-1"), Status.DONE)
        self.assertTrue(self.store.delete("task", t.id, actor="agent-1"))
        self.assertEqual(self.store.counts()["tasks"], 0)

    def test_filters(self):
        p1 = self.store.add_project("P1", priority="p0")
        p2 = self.store.add_project("P2", priority="p2")
        s1 = self.store.add_story(p1.id, "S1", priority="p0")
        s2 = self.store.add_story(p2.id, "S2")
        t1 = self.store.add_task(s1.id, "T1", priority="p1")
        self.store.add_task(s2.id, "T2")
        self.store.set_status("task", t1.id, Status.DONE)
        done = self.store.tree(status=Status.DONE)
        self.assertEqual(sum(len(ts) for _, stories in done for _, ts in stories), 1)
        only_p2 = self.store.tree(project_id=p2.id)
        self.assertEqual(len(only_p2), 1)
        self.assertEqual(only_p2[0][0].id, p2.id)
        pri = self.store.tree(priority="p0")
        self.assertEqual(len(pri), 1)
        self.assertEqual(pri[0][0].id, p1.id)

    def test_cli_update_delete_feed(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-project", "--title", "P1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-story", "--project", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-task", "--story", "1", "--title", "T1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "update", "--kind", "task", "--id", "1", "--title", "T1b"]),
            0,
        )
        self.assertEqual(self.store.get_task(1).title, "T1b")
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "doing"]),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "feed", "--limit", "3"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "delete", "--kind", "task", "--id", "1"]), 0)
        self.assertEqual(self.store.counts()["tasks"], 0)

    def test_status_rollup_cascade(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t1 = self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        self.store.set_status("task", t1.id, Status.DOING)
        self.assertEqual(self.store.get_story(s.id).status, Status.DOING)
        self.assertEqual(self.store.get_project(p.id).status, Status.DOING)
        self.store.set_status("task", t1.id, Status.DONE)
        self.assertEqual(self.store.get_story(s.id).status, Status.TODO)  # T2 still open
        self.assertEqual(self.store.get_project(p.id).status, Status.TODO)
        self.store.set_status("task", t2.id, Status.DONE)
        self.assertEqual(self.store.get_story(s.id).status, Status.DONE)
        self.assertEqual(self.store.get_project(p.id).status, Status.DONE)

    def test_rollup_empty_keeps_manual(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        self.assertTrue(self.store.set_status("story", s.id, Status.DONE))
        self.assertEqual(self.store.get_story(s.id).status, Status.DONE)  # no tasks: untouched
        # the done story rolls its project up (all children done -> done)
        self.assertEqual(self.store.get_project(p.id).status, Status.DONE)
        p2 = self.store.add_project("P2")  # no stories: manual sticks
        self.assertTrue(self.store.set_status("project", p2.id, Status.DOING))
        self.assertEqual(self.store.get_project(p2.id).status, Status.DOING)

    def test_manual_parent_yields_to_children(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        self.store.add_task(s.id, "T")
        self.assertTrue(self.store.set_status("story", s.id, Status.DONE))
        self.assertEqual(self.store.get_story(s.id).status, Status.TODO)  # rolled back

    def test_reconcile_fixes_drift(self):
        import sqlite3

        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        conn = sqlite3.connect(self.db)  # bypass rollup to simulate drift
        conn.execute("UPDATE stories SET status='done' WHERE id=?", (s.id,))
        conn.execute("UPDATE projects SET status='done' WHERE id=?", (p.id,))
        conn.commit()
        conn.close()
        changes = self.store.reconcile(actor="t")
        self.assertEqual(
            changes,
            [
                {"kind": "story", "id": s.id, "to": "todo"},
                {"kind": "project", "id": p.id, "to": "todo"},
            ],
        )
        self.assertEqual(self.store.get_story(s.id).status, Status.TODO)
        self.assertEqual(self.store.get_project(p.id).status, Status.TODO)
        self.assertEqual(self.store.reconcile(actor="t"), [])
        self.assertIsNotNone(t)

    def test_cli_status_and_reconcile(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-project", "--title", "P1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-story", "--project", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-task", "--story", "1", "--title", "T1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"]),
            0,
        )
        self.assertEqual(self.store.get_story(1).status, Status.DONE)
        self.assertEqual(self.store.get_project(1).status, Status.DONE)
        self.assertEqual(lpui_main(["--db", self.db, "reconcile"]), 0)

    def test_list_shows_all_by_default(self):
        import io
        import json
        from contextlib import redirect_stdout

        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        self.store.set_status("task", t2.id, Status.DONE)

        def _list_out(argv):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
            return buf.getvalue()

        bare = _list_out(["list"])
        self.assertIn("T1", bare)
        self.assertIn("T2", bare)
        everything = _list_out(["list", "--status", "all"])
        self.assertIn("T1", everything)
        self.assertIn("T2", everything)
        todo_only = _list_out(["list", "--status", "todo"])
        self.assertIn("T1", todo_only)
        self.assertNotIn("T2", todo_only)
        done_only = _list_out(["list", "--status", "done"])
        self.assertIn("T2", done_only)
        self.assertNotIn("T1", done_only)
        payload = json.loads(_list_out(["list", "--json"]))
        tasks = [
            t["task"]["title"] for entry in payload for s_ in entry["stories"] for t in s_["tasks"]
        ]
        self.assertEqual(sorted(tasks), ["T1", "T2"])

    def test_project_order_newest_first(self):
        a = self.store.add_project("Old")
        b = self.store.add_project("New")
        self.assertEqual([p.id for p in self.store.list_projects()], [b.id, a.id])
        tree = self.store.tree()
        self.assertEqual([p.id for p, _ in tree], [b.id, a.id])

    def test_new_tasks_default_p1(self):
        import io
        from contextlib import redirect_stdout

        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "NoPri")
        self.assertEqual(t.priority, "p1")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(
                lpui_main(["--db", self.db, "add-task", "--story", "1", "--title", "Cli"]), 0
            )
        self.assertEqual(self.store.get_task(2).priority, "p1")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(
                lpui_main(
                    [
                        "--db",
                        self.db,
                        "add-task",
                        "--story",
                        "1",
                        "--title",
                        "Exp",
                        "--priority",
                        "p0",
                    ]
                ),
                0,
            )
        self.assertEqual(self.store.get_task(3).priority, "p0")

    def test_archive_rule_and_view(self):
        import io
        import sqlite3
        import time
        from contextlib import redirect_stdout

        old = self.store.add_project("Old")
        fresh = self.store.add_project("Fresh")
        openp = self.store.add_project("Open")
        self.store.set_status("project", old.id, Status.DONE)
        self.store.set_status("project", fresh.id, Status.DONE)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE events SET ts=? WHERE kind='project' AND detail LIKE 'project #1%'",
            (time.time() - 90000,),
        )
        conn.commit()
        conn.close()
        self.assertTrue(self.store.is_archived(self.store.get_project(old.id)))
        self.assertFalse(self.store.is_archived(self.store.get_project(fresh.id)))
        self.assertFalse(self.store.is_archived(self.store.get_project(openp.id)))
        names = [p.name for p, _ in self.store.tree()]
        self.assertNotIn("Old", names)
        self.assertIn("Fresh", names)
        self.assertEqual([p.name for p, _ in self.store.tree(archived="only")], ["Old"])
        self.assertEqual(len(self.store.tree(archived="show")), 3)
        with self.assertRaises(ValueError):
            self.store.tree(archived="yesterday")

        def _list_out(argv):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
            return buf.getvalue()

        self.assertNotIn("Old", _list_out(["list"]))
        self.assertIn("Old", _list_out(["list", "--archived"]))
        self.assertNotIn("Fresh", _list_out(["list", "--archived"]))
        self.assertIn("Old", _list_out(["list", "--status", "all"]))

    def test_counts_by_state(self):
        self.store.add_project("Todo")
        p2 = self.store.add_project("Doing")
        p3 = self.store.add_project("Done")
        self.store.set_status("project", p2.id, Status.DOING)
        self.store.set_status("project", p3.id, Status.DONE)
        c = self.store.counts()
        self.assertEqual((c["projects_todo"], c["projects_doing"], c["projects_done"]), (1, 1, 1))
        self.assertEqual(c["projects"], 3)

    def test_removed_verbs_are_gone(self):
        import io
        from contextlib import redirect_stderr

        for argv in (
            ["gantt"],
            ["propose", "--kind", "task", "--parent", "1", "--title", "x"],
            ["ask", "--question", "q"],
            ["sync"],
            ["add-link", "--kind", "task", "--id", "1", "--url", "https://x"],
            ["add-risk", "--project", "1", "--title", "r"],
            ["add-milestone", "--project", "1", "--title", "m"],
        ):
            with self.subTest(argv=argv):
                buf = io.StringIO()
                with redirect_stderr(buf):
                    with self.assertRaises(SystemExit) as ctx:
                        lpui_main(["--db", self.db, *argv])
                self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
