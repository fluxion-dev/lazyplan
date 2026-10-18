import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan.cli import main as lpui_main
from lazyplan.gantt import bar, span
from lazyplan.models import RiskStatus, Status
from lazyplan.store import Store


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hierarchy(self):
        p = self.store.add_project("Site", start_date="2026-10-20", end_date="2026-12-01")
        s = self.store.add_story(p.id, "Home", start_date="2026-10-20", end_date="2026-11-01")
        t = self.store.add_task(s.id, "Hero", estimate="3d")
        self.assertEqual(self.store.counts()["tasks"], 1)
        tree = self.store.tree()
        self.assertEqual(tree[0][0].id, p.id)
        self.assertEqual(tree[0][1][0][1][0].id, t.id)
        self.assertTrue(self.store.set_status("task", t.id, Status.DONE))
        self.assertEqual(self.store.counts()["tasks_done"], 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.store.add_project("   ")
        with self.assertRaises(KeyError):
            self.store.add_story(999, "nope")
        with self.assertRaises(KeyError):
            self.store.add_task(999, "nope")

    def test_cli_json_ingress(self):
        rc = lpui_main(["--db", self.db, "--json", "add-project", "--name", "P1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-story", "--project", "1", "--title", "S1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-task", "--story", "1", "--title", "T1"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.counts()["tasks"], 1)

    def test_narrative_show_and_links(self):
        p = self.store.add_project(
            "P",
            goal="ship it",
            success_metrics="done",
            scope_in="a",
            scope_out="b",
            assumptions="c",
        )
        s = self.store.add_story(p.id, "S", owner="agent-1")
        t = self.store.add_task(s.id, "T", description="do the thing", owner="agent-1")
        self.store.update_project(p.id, goal="ship it well")
        self.assertEqual(self.store.get_project(p.id).goal, "ship it well")
        self.assertEqual(self.store.get_task(t.id).description, "do the thing")
        self.assertEqual(self.store.distinct_owners(), ["agent-1"])
        self.assertEqual(len(self.store.tree(owner="agent-1")[0][1]), 1)
        self.assertEqual(self.store.tree(owner="nobody"), [])
        li = self.store.add_link("story", s.id, "https://example.com/spec", "spec")
        self.assertEqual(li.id, 1)
        self.assertEqual(len(self.store.list_links("story", s.id)), 1)
        full = self.store.get_full("story", s.id)
        assert full is not None
        self.assertEqual(full["links"][0]["url"], "https://example.com/spec")
        self.assertEqual(len(full["tasks"]), 1)
        self.assertTrue(self.store.delete_link(li.id))
        self.assertEqual(self.store.list_links("story", s.id), [])
        with self.assertRaises(KeyError):
            self.store.add_link("story", 999, "https://x")
        with self.assertRaises(ValueError):
            self.store.add_link("project", p.id, "https://x")

    def test_link_cascade_on_delete(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.add_link("story", s.id, "https://s")
        self.store.add_link("task", t.id, "https://t")
        self.assertTrue(self.store.delete("story", s.id))
        self.assertEqual(self.store.list_links("story", s.id), [])
        self.assertEqual(self.store.list_links("task", t.id), [])

    def test_migration_from_old_db(self):
        import sqlite3

        legacy = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo');
        CREATE TABLE stories (id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo', start_date TEXT NOT NULL DEFAULT '',
            end_date TEXT NOT NULL DEFAULT '');
        CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
            estimate TEXT NOT NULL DEFAULT '');
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            actor TEXT NOT NULL DEFAULT 'human', kind TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '');
        INSERT INTO projects (name) VALUES ('Old');
        INSERT INTO stories (project_id, title) VALUES (1, 'OldS');
        INSERT INTO tasks (story_id, title) VALUES (1, 'OldT');
        """)
        conn.commit()
        conn.close()
        s = Store(legacy)  # must migrate, not crash
        self.assertEqual(s.get_project(1).name, "Old")
        self.assertEqual(s.get_project(1).goal, "")
        self.assertEqual(s.get_task(1).description, "")
        self.assertEqual(s.get_task(1).owner, "")
        self.assertEqual(s.counts()["tasks"], 1)

    def test_planning_fields_sort_and_guards(self):
        p = self.store.add_project("P")
        low = self.store.add_story(p.id, "Low", priority="p2", labels="UI, ui, backend")
        high = self.store.add_story(p.id, "High", priority="p0")
        self.assertEqual([s.title for s in self.store.list_stories(p.id)], ["High", "Low"])
        self.assertEqual(low.labels, ["ui", "backend"])
        with self.assertRaises(ValueError):
            self.store.add_story(p.id, "Bad", priority="p9")
        t1 = self.store.add_task(high.id, "T1")
        t2 = self.store.add_task(high.id, "T2", blocked_by=str(t1.id))
        self.assertTrue(self.store.is_blocked("task", t2.id))
        self.store.set_status("task", t1.id, Status.DONE)
        self.assertFalse(self.store.is_blocked("task", t2.id))
        with self.assertRaises(ValueError):
            self.store.update_task(t1.id, blocked_by=str(t2.id))  # cycle
        with self.assertRaises(ValueError):
            self.store.update_task(t1.id, blocked_by=str(t1.id))  # self
        with self.assertRaises(KeyError):
            self.store.update_task(t1.id, blocked_by="4242")
        est = self.store.update_story(high.id, estimate="~2w")
        assert est is not None
        self.assertEqual(est.estimate, "~2w")
        self.assertEqual(len(self.store.tree(priority="p0")[0][1]), 1)

    def test_criteria_risks_milestones(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        c1 = self.store.add_criteria("task", t.id, "works")
        c2 = self.store.add_criteria("task", t.id, "fast")
        self.assertEqual(self.store.criteria_progress("task", t.id), (0, 2))
        self.store.set_criteria(c1.id, True)
        self.assertEqual(self.store.criteria_progress("task", t.id), (1, 2))
        self.assertEqual(len(self.store.open_criteria("task", t.id)), 1)
        self.assertTrue(self.store.delete_criteria(c2.id))
        with self.assertRaises(KeyError):
            self.store.add_criteria("task", 999, "x")
        r = self.store.add_risk(p.id, "slip", likelihood="high", impact="high")
        self.assertEqual(self.store.list_risks(p.id)[0].id, r.id)
        self.store.set_risk(r.id, status=RiskStatus.MITIGATED, mitigation="buffer")
        self.assertEqual(self.store.set_risk(r.id).status, RiskStatus.MITIGATED)
        m = self.store.add_milestone(p.id, "Beta", "2026-11-15")
        self.assertEqual(self.store.list_milestones(p.id)[0].id, m.id)
        full = self.store.get_full("project", p.id)
        assert full is not None
        self.assertEqual(len(full["risks"]), 1)
        self.assertEqual(len(full["milestones"]), 1)
        self.assertTrue(self.store.delete_milestone(m.id))

    def test_sync_to_postgres_live(self):
        dsn = os.environ.get("LAZYPLAN_TEST_PG_DSN", "")
        if not dsn:
            self.skipTest("no live postgres (set LAZYPLAN_TEST_PG_DSN)")
        try:
            import psycopg  # noqa: F401
        except ImportError:
            self.skipTest("psycopg not installed")
        from lazyplan.postgres_sync import sync_sqlite_to_pg

        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.add_criteria("task", t.id, "works")
        counts = sync_sqlite_to_pg(str(self.store.path), dsn)
        self.assertEqual(counts["tasks"], 1)
        import psycopg as _pg

        with _pg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute("SELECT title FROM tasks WHERE id=%s", (t.id,))
            self.assertEqual(cur.fetchone()[0], "T")

    def test_export_import_roundtrip(self):
        p = self.store.add_project("P", goal="g")
        self.store.set_status("project", p.id, Status.DOING)
        s = self.store.add_story(p.id, "S", priority="p1")
        b = self.store.add_story(p.id, "B")
        self.store.update_story(s.id, blocked_by=str(b.id))
        t = self.store.add_task(s.id, "T", description="d")
        self.store.set_status("task", t.id, Status.DONE)
        self.store.add_criteria("task", t.id, "works")
        self.store.add_risk(p.id, "r1")
        self.store.add_milestone(p.id, "M1", "2026-12-01")
        self.store.add_link("story", s.id, "https://ex.com")
        data = self.store.export_all()
        import tempfile

        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        counts = s2.import_all(data)
        self.assertEqual(
            counts,
            {
                "projects": 1,
                "stories": 2,
                "tasks": 1,
                "links": 1,
                "criteria": 1,
                "risks": 1,
                "milestones": 1,
            },
        )
        self.assertEqual(s2.get_project(1).status, Status.DOING)
        self.assertEqual(s2.get_project(1).goal, "g")
        self.assertEqual(s2.get_task(1).description, "d")
        self.assertEqual(s2.get_task(1).status, Status.DONE)
        self.assertEqual(s2.criteria_progress("task", 1), (0, 1))
        full = s2.get_full("story", 1)
        assert full is not None
        self.assertEqual(full["story"]["blocked_by"], [b.id])
        with self.assertRaises(ValueError):
            s2.import_all({"nope": True})

    def test_cli_planning_surface(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-project", "--name", "P1"]), 0)
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
                    "--labels",
                    "a,b",
                    "--estimate",
                    "big",
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
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "update", "--kind", "task", "--id", "1", "--blocked-by", ""]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "list", "--priority", "p0"]), 0)
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "add-criteria", "--kind", "task", "--id", "1", "--text", "works"]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "criteria", "--kind", "task", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "check", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "uncheck", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-risk",
                    "--project",
                    "1",
                    "--title",
                    "slip",
                    "--likelihood",
                    "high",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "risks", "--project", "1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "risk-status", "--id", "1", "--to", "mitigated"]), 0
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-milestone",
                    "--project",
                    "1",
                    "--title",
                    "Beta",
                    "--date",
                    "2026-11-15",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "milestones", "--project", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "gantt", "--tasks", "--width", "20"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "export", "--format", "markdown"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"]), 0
        )  # warns, proceeds
        self.assertEqual(lpui_main(["--db", self.db, "delete-criteria", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "delete-milestone", "--id", "1"]), 0)

    def test_proposals_and_questions(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S")
        pr = self.store.propose("task", s.id, {"title": "PT", "priority": "p1"}, actor="agent-1")
        self.assertEqual(pr["status"], "pending")
        with self.assertRaises(KeyError):
            self.store.propose("task", 999, {"title": "x"})
        with self.assertRaises(ValueError):
            self.store.propose("task", s.id, {"title": "  "})
        res = self.store.decide_proposal(pr["id"], True, actor="human")
        assert res is not None
        self.assertEqual(res["status"], "applied")
        self.assertEqual(self.store.get_task(res["result_id"]).priority, "p1")
        pr2 = self.store.propose("story", p.id, {"title": "PS"}, actor="agent-1")
        self.store.decide_proposal(pr2["id"], False)
        self.assertEqual(self.store.list_proposals("pending"), [])
        with self.assertRaises(ValueError):
            self.store.decide_proposal(pr2["id"], True)  # already rejected
        q = self.store.ask("agent-1", "Which?")
        self.assertEqual(len(self.store.list_questions()), 1)
        self.store.answer_question(q["id"], "Blue", actor="human")
        self.assertEqual(self.store.list_questions(), [])
        self.assertEqual(len(self.store.list_questions(open_only=False)), 1)

    def test_cli_proposals_questions(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-project", "--name", "P"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-story", "--project", "1", "--title", "S"]), 0
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "--actor",
                    "agent-1",
                    "propose",
                    "--kind",
                    "task",
                    "--parent",
                    "1",
                    "--title",
                    "PT",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "proposals"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "reject", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "--actor", "agent-1", "ask", "--question", "Q?"]), 0
        )
        self.assertEqual(lpui_main(["--db", self.db, "questions"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "answer", "--id", "1", "--text", "A"]), 0)

    def test_critical_path(self):
        p = self.store.add_project("P")
        a = self.store.add_story(p.id, "A", start_date="2026-01-01", end_date="2026-01-10")
        b = self.store.add_story(
            p.id, "B", start_date="2026-01-05", end_date="2026-01-06", blocked_by=str(a.id)
        )
        c = self.store.add_story(p.id, "C", blocked_by=str(b.id))
        self.assertEqual(self.store.critical_path(p.id), [a.id, b.id, c.id])
        full = self.store.get_full("project", p.id)
        assert full is not None
        self.assertEqual(full["critical"], [a.id, b.id, c.id])

    def test_cli_show_and_links(self):
        self.assertEqual(
            lpui_main(["--db", self.db, "add-project", "--name", "P1", "--goal", "g1"]), 0
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
                    "--owner",
                    "agent-9",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "add-task", "--story", "1", "--title", "T1", "--desc", "d1"]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-link",
                    "--kind",
                    "story",
                    "--id",
                    "1",
                    "--url",
                    "https://ex.com",
                    "--label",
                    "spec",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "links", "--kind", "story", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "show", "--kind", "project", "--id", "1"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "show", "--kind", "story", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "update",
                    "--kind",
                    "task",
                    "--id",
                    "1",
                    "--owner",
                    "agent-9",
                    "--desc",
                    "d2",
                ]
            ),
            0,
        )
        self.assertEqual(self.store.get_task(1).owner, "agent-9")
        self.assertEqual(lpui_main(["--db", self.db, "list", "--owner", "agent-9"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "delete-link", "--id", "1"]), 0)

    def test_task_dates_and_update(self):
        p = self.store.add_project("P")
        s = self.store.add_story(p.id, "S", start_date="2026-10-20", end_date="2026-11-01")
        t = self.store.add_task(s.id, "T", start_date="2026-10-21", end_date="2026-10-25")
        self.assertEqual(t.start_date, "2026-10-21")
        upd = self.store.update_task(t.id, title="T2", estimate="2d")
        assert upd is not None
        self.assertEqual(upd.title, "T2")
        self.assertEqual(self.store.get_task(t.id).estimate, "2d")
        dates = ["2026-10-20", "2026-11-01", "2026-10-21", "2026-10-25"]
        lo, hi = span(dates)
        self.assertIn("█", bar("2026-10-21", "2026-10-25", lo, hi))

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
        p1 = self.store.add_project("P1")
        p2 = self.store.add_project("P2")
        s1 = self.store.add_story(p1.id, "S1")
        s2 = self.store.add_story(p2.id, "S2")
        t1 = self.store.add_task(s1.id, "T1")
        self.store.add_task(s2.id, "T2")
        self.store.set_status("task", t1.id, Status.DONE)
        done = self.store.tree(status=Status.DONE)
        self.assertEqual(sum(len(ts) for _, stories in done for _, ts in stories), 1)
        only_p2 = self.store.tree(project_id=p2.id)
        self.assertEqual(len(only_p2), 1)
        self.assertEqual(only_p2[0][0].id, p2.id)

    def test_cli_update_delete_feed(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-project", "--name", "P1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-story", "--project", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-task", "--story", "1", "--title", "T1"]), 0
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "update",
                    "--kind",
                    "task",
                    "--id",
                    "1",
                    "--title",
                    "T1b",
                    "--estimate",
                    "1d",
                ]
            ),
            0,
        )
        self.assertEqual(self.store.get_task(1).title, "T1b")
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "doing"]),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "feed", "--limit", "3"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "gantt", "--tasks", "--width", "20"]), 0)
        self.assertEqual(lpui_main(["--db", self.db, "delete", "--kind", "task", "--id", "1"]), 0)
        self.assertEqual(self.store.counts()["tasks"], 0)


if __name__ == "__main__":
    unittest.main()
