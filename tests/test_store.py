import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import migrate as migrate_mod
from lazyplan import services
from lazyplan.cli import main as lpui_main
from lazyplan.models import Status
from lazyplan.store import Store, default_actor


class TestDefaultActor(unittest.TestCase):
    def test_login_name_on_posix_and_windows(self):
        for env, want in (
            ({"USER": "ana"}, "ana"),
            ({"USERNAME": "bo"}, "bo"),
            ({"USER": "ana", "USERNAME": "bo"}, "ana"),
            ({}, "human"),
        ):
            with self.subTest(env=env), mock.patch.dict(os.environ, clear=False):
                os.environ.pop("USER", None)
                os.environ.pop("USERNAME", None)
                os.environ.update(env)
                self.assertEqual(default_actor(), want)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_version_and_indexes(self):
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                int(conn.execute("PRAGMA user_version").fetchone()[0]),
                migrate_mod.SCHEMA_VERSION,
            )
            names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            }
        for name in (
            "idx_events_action",
            "idx_vcs_links_sha",
            "idx_issue_links_row",
            "idx_entity_repos_branch",
        ):
            self.assertIn(name, names)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.row_factory = sqlite3.Row
            with mock.patch.object(migrate_mod, "_migrate_elements") as legacy:
                migrate_mod.migrate(conn)
        legacy.assert_not_called()

    def test_writes_release_the_database_file(self):
        self.store.add_plan("Site")
        self.store.list_plans()
        os.replace(self.db, self.db + ".moved")
        self.assertTrue(os.path.isfile(self.db + ".moved"))

    def test_show_reads_through_one_connection(self):
        plan = self.store.add_plan("Site")
        milestone = self.store.add_milestone(plan.id, "Home")
        for index in range(5):
            self.store.add_task(milestone.id, f"T{index}")
        with mock.patch("lazyplan.store.sqlite3.connect", wraps=sqlite3.connect) as connect:
            self.assertIsNotNone(self.store.get_full("plan", plan.id))
        self.assertEqual(connect.call_count, 1)

    def test_other_threads_never_share_the_open_connection(self):
        self.store.add_plan("Site")
        seen: list[int] = []
        with self.store._connect():
            worker = threading.Thread(target=lambda: seen.append(len(self.store.list_plans())))
            worker.start()
            worker.join()
        self.assertEqual(seen, [1])

    def test_hierarchy(self):
        p = self.store.add_plan("Site", goal="why")
        s = self.store.add_milestone(p.id, "Home")
        t = self.store.add_task(s.id, "Hero", description="do it")
        self.assertEqual(self.store.counts()["tasks"], 1)
        tree = services.tree(
            self.store,
        )
        self.assertEqual(tree[0][0].id, p.id)
        self.assertEqual(tree[0][1][0][1][0].id, t.id)
        self.assertTrue(services.set_status(self.store, "task", t.id, Status.DONE))
        self.assertEqual(self.store.counts()["tasks_done"], 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.store.add_plan("   ")
        with self.assertRaises(KeyError):
            self.store.add_milestone(999, "nope")
        with self.assertRaises(KeyError):
            self.store.add_task(999, "nope")

    def test_cli_json_ingress(self):
        rc = lpui_main(["--db", self.db, "--json", "add-plan", "--title", "P1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-milestone", "--plan", "1", "--title", "S1"])
        self.assertEqual(rc, 0)
        rc = lpui_main(["--db", self.db, "--json", "add-task", "--milestone", "1", "--title", "T1"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.store.counts()["tasks"], 1)

    def test_plan_why_what(self):
        p = self.store.add_plan("P", description="the what", goal="the why")
        self.assertEqual(self.store.get_plan(p.id).goal, "the why")
        upd = self.store.update_plan(p.id, goal="why v2")
        assert upd is not None
        self.assertEqual(upd.goal, "why v2")

    def test_creation_order(self):
        p = self.store.add_plan("P")
        self.store.add_milestone(p.id, "First")
        self.store.add_milestone(p.id, "Second")
        self.assertEqual([s.title for s in self.store.list_milestones(p.id)], ["First", "Second"])
        s = self.store.list_milestones(p.id)[0]
        self.store.add_task(s.id, "A")
        self.store.add_task(s.id, "B")
        self.assertEqual([t.title for t in self.store.list_tasks(s.id)], ["A", "B"])

    def test_bulk_maps_match_per_id_reads(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t1 = self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        self.store.add_criteria("plan", p.id, "plan criterion")
        self.store.add_criteria("milestone", s.id, "milestone criterion")
        self.store.add_criteria("task", t1.id, "open task criterion")
        done = self.store.add_criteria("task", t2.id, "done task criterion")
        self.store.set_criteria(done.id, True)
        self.store.link_commit("task", t1.id, "a" * 40)
        issue = self.store.add_issue_link(
            "github", "42", "42", "https://example.test/42", "Issue 42", "open", "task", t1.id
        )
        self.store.log("bench", "plan", "status", f"plan #{p.id} -> doing")
        self.store.log("bench", "plan", "status", f"plan #{p.id} -> done (rollup)")

        self.assertEqual(self.store.milestones_map(), {p.id: self.store.list_milestones(p.id)})
        self.assertEqual(
            self.store.tasks_map(),
            {s.id: self.store.list_tasks(s.id)},
        )
        expected_criteria = {
            ("plan", p.id): self.store.list_criteria("plan", p.id),
            ("milestone", s.id): self.store.list_criteria("milestone", s.id),
            ("task", t1.id): self.store.list_criteria("task", t1.id),
            ("task", t2.id): self.store.list_criteria("task", t2.id),
        }
        self.assertEqual(self.store.criteria_map(), expected_criteria)
        self.assertEqual(self.store.open_task_criteria_ids(), {t1.id})
        self.assertEqual(
            self.store.issue_links_map(),
            {("task", t1.id): [issue]},
        )
        self.assertEqual(self.store.plan_status_events_map()[p.id][1], "done")

    def test_get_full_many_matches_single_reads(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t1 = self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        for kind, obj_id in (("plan", p.id), ("milestone", s.id), ("task", t1.id)):
            self.store.add_criteria(kind, obj_id, "works")
        self.store.add_note("task", t1.id, "handoff", actor="bench")
        self.store.add_comment("task", t1.id, "review", actor="bench")
        self.store.add_issue_link(
            "github", "42", "42", "https://example.test/42", "Issue 42", "open", "task", t1.id
        )
        self.store.link_commit("task", t1.id, "a" * 40, subject="work", files=("a.py",))
        self.store.link_forge("task", t2.id, 7, title="PR", state="open", checks="pass")
        self.store.add_repo_link("plan", p.id, "/checkout/plan", "git@example.test:org/plan.git")
        self.store.add_repo_link("task", t1.id, "/checkout/task", "git@example.test:org/task.git")
        self.store.claim_task(t1.id, "agent")

        for kind, ids in (
            ("plan", [p.id]),
            ("milestone", [s.id]),
            ("task", [t1.id, t2.id]),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(
                    self.store.get_full_many(kind, ids),
                    [self.store.get_full(kind, obj_id) for obj_id in ids],
                )

    def test_cli_list_json_matches_store_reads(self):
        from lazyplan.cli import _list_payload

        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        criterion = self.store.add_criteria("task", t.id, "works")
        self.store.link_commit("task", t.id, "a" * 40)
        self.store.add_repo_link("plan", p.id, "/checkout/plan", "git@example.test:org/plan.git")
        self.store.add_repo_link("task", t.id, "/checkout/task", "git@example.test:org/task.git")

        payload = _list_payload(self.store, None, "show", None, None, None, None)
        self.assertEqual(len(payload), 1)
        entry = payload[0]
        self.assertEqual(entry["criteria"], [])
        self.assertEqual(entry["links"], [])
        self.assertEqual(entry["repos"], self.store.list_repos("plan", p.id))
        milestone = entry["milestones"][0]
        task = milestone["tasks"][0]
        self.assertEqual(task["criteria"], [vars(criterion)])
        self.assertEqual(
            task["links"], [vars(link) for link in self.store.list_links("task", t.id)]
        )
        self.assertEqual(task["repos"], self.store.list_repos("task", t.id))
        self.assertEqual(task["effective_repos"], self.store.effective_repos("task", t.id))
        self.assertEqual(
            milestone["effective_repos"], self.store.effective_repos("milestone", s.id)
        )

    def test_import_is_atomic_on_failure(self):
        data = {
            "lazyplan": 1,
            "plans": [
                {"plan": {"name": "Good"}},
                {"not_a_plan": True},
            ],
        }
        with self.assertRaises(KeyError):
            services.import_all(self.store, data)
        self.assertEqual(self.store.counts()["plans"], 0)

    def test_export_plan_does_not_export_everything(self):
        p = self.store.add_plan("P")
        with mock.patch.object(services, "export_all", side_effect=AssertionError("full export")):
            entry = services.export_plan(self.store, p.id)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry["plan"]["id"], p.id)

    def test_criteria_on_plan_milestone_task(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        for kind, oid in (("plan", p.id), ("milestone", s.id), ("task", t.id)):
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
            self.store.add_criteria("plan", 999, "x")
        with self.assertRaises(ValueError):
            self.store.add_criteria("nope", 1, "x")

    def test_criteria_cascade_on_delete(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        self.store.add_criteria("plan", p.id, "pc")
        self.store.add_criteria("milestone", s.id, "sc")
        self.store.add_criteria("task", t.id, "tc")
        self.assertTrue(self.store.delete("plan", p.id))
        self.assertEqual(self.store.list_criteria("plan", p.id), [])
        self.assertEqual(self.store.list_criteria("milestone", s.id), [])
        self.assertEqual(self.store.list_criteria("task", t.id), [])

    def test_migration_from_old_db(self):
        import sqlite3

        legacy = os.path.join(self.tmp.name, "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
            goal TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '');
        CREATE TABLE stories (id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo', priority TEXT NOT NULL DEFAULT '');
        CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
            title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'todo',
            description TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '');
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
        self.assertEqual(s.get_plan(1).name, "Old")
        self.assertEqual(s.get_plan(1).goal, "old-why")
        with closing(sqlite3.connect(legacy)) as conn:
            legacy_cols = {row[1] for row in conn.execute("PRAGMA table_info(plans)")}
        self.assertNotIn("priority", legacy_cols)
        self.assertEqual(s.get_task(1).description, "")
        self.assertEqual(s.get_milestone(1).plan_id, 1)
        self.assertEqual(s.get_task(1).milestone_id, 1)
        self.assertEqual(s.list_criteria("milestone", 1)[0].text, "old-crit")
        # plan-level criteria now allowed on the migrated table
        c = s.add_criteria("plan", 1, "new-crit")
        self.assertEqual(c.text, "new-crit")
        self.assertEqual(s.counts()["tasks"], 1)

    def test_migration_drops_empty_legacy_milestones_table(self):
        import sqlite3

        legacy = os.path.join(self.tmp.name, "legacy2.db")
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO projects (name) VALUES ('Old')")
        conn.execute(
            "CREATE TABLE milestones (id INTEGER PRIMARY KEY,"
            " project_id INTEGER, title TEXT, date TEXT)"
        )
        conn.commit()
        conn.close()
        s = Store(legacy)
        self.assertEqual([p.name for p in s.list_plans()], ["Old"])
        with closing(sqlite3.connect(legacy)) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(milestones)").fetchall()}
        self.assertIn("plan_id", cols)
        self.assertNotIn("project_id", cols)

    def test_migration_refuses_nonempty_legacy_milestones_table(self):
        import sqlite3

        legacy = os.path.join(self.tmp.name, "legacy3.db")
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute(
            "CREATE TABLE milestones (id INTEGER PRIMARY KEY,"
            " project_id INTEGER, title TEXT, date TEXT)"
        )
        conn.execute("INSERT INTO milestones (project_id, title) VALUES (1, 'X')")
        conn.commit()
        conn.close()
        with self.assertRaises(RuntimeError):
            Store(legacy)

    def test_export_import_roundtrip(self):
        p = self.store.add_plan("P", goal="g")
        services.set_status(self.store, "plan", p.id, Status.DOING)
        s = self.store.add_milestone(p.id, "S")
        self.store.add_criteria("plan", p.id, "pcrit")
        t = self.store.add_task(s.id, "T", description="d")
        services.set_status(self.store, "task", t.id, Status.DONE)
        self.store.add_criteria("task", t.id, "works")
        data = services.export_all(self.store)
        import tempfile

        db2 = os.path.join(tempfile.mkdtemp(), "imp.db")
        s2 = Store(db2)
        counts = services.import_all(s2, data)
        self.assertEqual(
            counts,
            {
                "plans": 1,
                "milestones": 1,
                "tasks": 1,
                "criteria": 2,
                "links": 0,
                "repos": 0,
                "forge_links": 0,
                "claims": 0,
                "notes": 0,
                "criterion_links": 0,
                "comments": 0,
                "issues": 0,
            },
        )
        self.assertEqual(s2.get_plan(1).status, Status.DONE)  # rolled up: only milestone done
        self.assertEqual(s2.get_milestone(1).status, Status.DONE)  # rolled up: its task is done
        self.assertEqual(s2.get_plan(1).goal, "g")
        self.assertEqual(s2.get_task(1).description, "d")
        self.assertEqual(s2.get_task(1).status, Status.DONE)
        self.assertEqual(s2.criteria_progress("plan", 1), (0, 1))
        self.assertEqual(s2.criteria_progress("task", 1), (0, 1))
        with self.assertRaises(ValueError):
            services.import_all(s2, {"nope": True})

    def test_cli_planning_surface(self):
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-plan",
                    "--title",
                    "P1",
                    "--why",
                    "w",
                    "--what",
                    "x",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-milestone",
                    "--plan",
                    "1",
                    "--title",
                    "S1",
                    "--desc",
                    "d",
                ]
            ),
            0,
        )
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-task",
                    "--milestone",
                    "1",
                    "--title",
                    "T1",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "list"]), 0)
        self.assertEqual(
            lpui_main(
                [
                    "--db",
                    self.db,
                    "add-criteria",
                    "--kind",
                    "plan",
                    "--id",
                    "1",
                    "--text",
                    "works",
                ]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "criteria", "--kind", "plan", "--id", "1"]), 0)
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
                    "plan",
                    "--id",
                    "1",
                    "--why",
                    "w2",
                ]
            ),
            0,
        )
        self.assertEqual(self.store.get_plan(1).goal, "w2")

    def test_cli_show(self):
        self.assertEqual(
            lpui_main(["--db", self.db, "add-plan", "--title", "P1", "--why", "g1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-milestone", "--plan", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(
                ["--db", self.db, "add-task", "--milestone", "1", "--title", "T1", "--desc", "d1"]
            ),
            0,
        )
        self.assertEqual(lpui_main(["--db", self.db, "show", "--kind", "plan", "--id", "1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "show", "--kind", "milestone", "--id", "1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "update", "--kind", "task", "--id", "1", "--desc", "d2"]),
            0,
        )
        self.assertEqual(self.store.get_task(1).description, "d2")

    def test_events_and_fingerprint(self):
        fp0 = self.store.fingerprint()
        p = self.store.add_plan("P", actor="agent-1")
        fp1 = self.store.fingerprint()
        self.assertNotEqual(fp0, fp1)
        events = self.store.feed(5)
        self.assertTrue(any(e["actor"] == "agent-1" and e["kind"] == "plan" for e in events))
        s = self.store.add_milestone(p.id, "S", actor="agent-1")
        t = self.store.add_task(s.id, "T", actor="agent-1")
        self.assertEqual(
            services.cycle_status(self.store, "task", t.id, actor="agent-1"), Status.DOING
        )
        self.assertEqual(
            services.cycle_status(self.store, "task", t.id, actor="agent-1"), Status.DONE
        )
        self.assertTrue(self.store.delete("task", t.id, actor="agent-1"))
        self.assertEqual(self.store.counts()["tasks"], 0)

    def test_tree_orders_by_recent_activity_with_id_fallback(self):
        ids = [self.store.add_plan(f"P{i}").id for i in range(7)]
        # touch the oldest plan last: it jumps to the front
        m = self.store.add_milestone(ids[0], "M")
        t = self.store.add_task(m.id, "T")
        services.set_status(self.store, "task", t.id, Status.DOING)
        ordered = [
            p.id
            for p, _ in services.tree(
                self.store,
            )
        ]
        self.assertEqual(ordered[0], ids[0])
        self.assertEqual(ordered[1:], ids[:0:-1])

    def test_tree_limit_caps_and_plan_id_bypasses(self):
        ids = [self.store.add_plan(f"P{i}").id for i in range(7)]
        self.assertEqual(len(services.tree(self.store, limit=5)), 5)
        self.assertEqual(len(services.tree(self.store, limit=2)), 2)
        self.assertEqual(len(services.tree(self.store, limit=0)), 0)
        pinned = services.tree(self.store, plan_id=ids[0], limit=1)
        self.assertEqual([p.id for p, _ in pinned], [ids[0]])

    def test_tree_repo_filter_uses_inherited_links(self):
        p1 = self.store.add_plan("P1")
        p2 = self.store.add_plan("P2")
        s1 = self.store.add_milestone(p1.id, "S1")
        s2 = self.store.add_milestone(p2.id, "S2")
        self.store.add_task(s1.id, "T1")
        t2 = self.store.add_task(s2.id, "T2")
        self.store.add_repo_link("plan", p1.id, "/checkout/one", "git@example.com:org/one.git")
        self.store.add_repo_link("task", t2.id, "/checkout/two", "git@example.com:org/two.git")

        self.assertEqual(
            [plan.id for plan, _ in services.tree(self.store, repo="/checkout/one")],
            [p1.id],
        )
        self.assertEqual(
            [plan.id for plan, _ in services.tree(self.store, repo="org/two")],
            [p2.id],
        )
        self.assertEqual(len(services.tree(self.store, repo="/checkout/three")), 0)

    def test_filters(self):
        p1 = self.store.add_plan("P1")
        p2 = self.store.add_plan("P2")
        s1 = self.store.add_milestone(p1.id, "S1")
        s2 = self.store.add_milestone(p2.id, "S2")
        t1 = self.store.add_task(s1.id, "T1")
        self.store.add_task(s2.id, "T2")
        services.set_status(self.store, "task", t1.id, Status.DONE)
        done = services.tree(self.store, status=Status.DONE)
        self.assertEqual(sum(len(ts) for _, milestones in done for _, ts in milestones), 1)
        only_p2 = services.tree(self.store, plan_id=p2.id)
        self.assertEqual(len(only_p2), 1)
        self.assertEqual(only_p2[0][0].id, p2.id)

    def test_cli_list_cap_flags(self):
        import io
        from contextlib import redirect_stdout

        for i in range(7):
            self.assertEqual(lpui_main(["--db", self.db, "add-plan", "--title", f"P{i}"]), 0)

        def _lines(*argv: str) -> list[str]:
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
            return [line for line in buf.getvalue().splitlines() if line.strip()]

        default_rows = [line for line in _lines("list") if line.startswith(("○", "◐", "●"))]
        self.assertEqual(len(default_rows), 5)
        all_rows = [line for line in _lines("list", "--all") if line.startswith(("○", "◐", "●"))]
        self.assertEqual(len(all_rows), 7)
        limited = [
            line for line in _lines("list", "--limit", "2") if line.startswith(("○", "◐", "●"))
        ]
        self.assertEqual(len(limited), 2)
        pinned = [
            line for line in _lines("list", "--plan", "1") if line.startswith(("○", "◐", "●"))
        ]
        self.assertEqual(len(pinned), 1)

    def test_cli_list_json_complete_unless_limited(self):
        import io
        import json
        from contextlib import redirect_stdout

        for i in range(7):
            self.assertEqual(lpui_main(["--db", self.db, "add-plan", "--title", f"J{i}"]), 0)

        def _json(*argv: str) -> list:
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
            return json.loads(buf.getvalue())

        self.assertEqual(len(_json("list", "--json")), 7)
        self.assertEqual(len(_json("list", "--json", "--limit", "2")), 2)

    def test_cli_update_delete_feed(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-plan", "--title", "P1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-milestone", "--plan", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-task", "--milestone", "1", "--title", "T1"]), 0
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
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t1 = self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        services.set_status(self.store, "task", t1.id, Status.DOING)
        self.assertEqual(self.store.get_milestone(s.id).status, Status.DOING)
        self.assertEqual(self.store.get_plan(p.id).status, Status.DOING)
        services.set_status(self.store, "task", t1.id, Status.DONE)
        self.assertEqual(self.store.get_milestone(s.id).status, Status.TODO)  # T2 still open
        self.assertEqual(self.store.get_plan(p.id).status, Status.TODO)
        services.set_status(self.store, "task", t2.id, Status.DONE)
        self.assertEqual(self.store.get_milestone(s.id).status, Status.DONE)
        self.assertEqual(self.store.get_plan(p.id).status, Status.DONE)

    def test_rollup_empty_keeps_manual(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        self.assertTrue(services.set_status(self.store, "milestone", s.id, Status.DONE))
        self.assertEqual(self.store.get_milestone(s.id).status, Status.DONE)  # no tasks: untouched
        # the done milestone rolls its plan up (all children done -> done)
        self.assertEqual(self.store.get_plan(p.id).status, Status.DONE)
        p2 = self.store.add_plan("P2")  # no milestones: manual sticks
        self.assertTrue(services.set_status(self.store, "plan", p2.id, Status.DOING))
        self.assertEqual(self.store.get_plan(p2.id).status, Status.DOING)

    def test_manual_parent_yields_to_children(self):
        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        self.store.add_task(s.id, "T")
        self.assertTrue(services.set_status(self.store, "milestone", s.id, Status.DONE))
        self.assertEqual(self.store.get_milestone(s.id).status, Status.TODO)  # rolled back

    def test_reconcile_fixes_drift(self):
        import sqlite3

        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        t = self.store.add_task(s.id, "T")
        conn = sqlite3.connect(self.db)  # bypass rollup to simulate drift
        conn.execute("UPDATE milestones SET status='done' WHERE id=?", (s.id,))
        conn.execute("UPDATE plans SET status='done' WHERE id=?", (p.id,))
        conn.commit()
        conn.close()
        changes = services.reconcile(self.store, actor="t")
        self.assertEqual(
            changes,
            [
                {"kind": "milestone", "id": s.id, "to": "todo"},
                {"kind": "plan", "id": p.id, "to": "todo"},
            ],
        )
        self.assertEqual(self.store.get_milestone(s.id).status, Status.TODO)
        self.assertEqual(self.store.get_plan(p.id).status, Status.TODO)
        self.assertEqual(services.reconcile(self.store, actor="t"), [])
        self.assertIsNotNone(t)

    def test_cli_status_and_reconcile(self):
        self.assertEqual(lpui_main(["--db", self.db, "add-plan", "--title", "P1"]), 0)
        self.assertEqual(
            lpui_main(["--db", self.db, "add-milestone", "--plan", "1", "--title", "S1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "add-task", "--milestone", "1", "--title", "T1"]), 0
        )
        self.assertEqual(
            lpui_main(["--db", self.db, "status", "--kind", "task", "--id", "1", "--to", "done"]),
            0,
        )
        self.assertEqual(self.store.get_milestone(1).status, Status.DONE)
        self.assertEqual(self.store.get_plan(1).status, Status.DONE)
        self.assertEqual(lpui_main(["--db", self.db, "reconcile"]), 0)

    def test_list_shows_all_by_default(self):
        import io
        import json
        from contextlib import redirect_stdout

        p = self.store.add_plan("P")
        s = self.store.add_milestone(p.id, "S")
        self.store.add_task(s.id, "T1")
        t2 = self.store.add_task(s.id, "T2")
        services.set_status(self.store, "task", t2.id, Status.DONE)

        def _list_out(argv):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(lpui_main(["--db", self.db, *argv]), 0)
            return buf.getvalue()

        bare = _list_out(["list", "--tree"])
        self.assertIn("T1", bare)
        self.assertIn("T2", bare)
        everything = _list_out(["list", "--tree", "--status", "all"])
        self.assertIn("T1", everything)
        self.assertIn("T2", everything)
        todo_only = _list_out(["list", "--tree", "--status", "todo"])
        self.assertIn("T1", todo_only)
        self.assertNotIn("T2", todo_only)
        done_only = _list_out(["list", "--tree", "--status", "done"])
        self.assertIn("T2", done_only)
        self.assertNotIn("T1", done_only)
        payload = json.loads(_list_out(["list", "--json"]))
        tasks = [
            t["task"]["title"]
            for entry in payload
            for s_ in entry["milestones"]
            for t in s_["tasks"]
        ]
        self.assertEqual(sorted(tasks), ["T1", "T2"])

    def test_plan_order_newest_first(self):
        a = self.store.add_plan("Old")
        b = self.store.add_plan("New")
        self.assertEqual([p.id for p in self.store.list_plans()], [b.id, a.id])
        tree = services.tree(
            self.store,
        )
        self.assertEqual([p.id for p, _ in tree], [b.id, a.id])

    def test_cli_rejects_priority_flag(self):
        with self.assertRaises(SystemExit):
            lpui_main(
                ["--db", self.db, "add-plan", "--title", "P", "--why", "w", "--priority", "p0"]
            )

    def test_archive_rule_and_view(self):
        import io
        import sqlite3
        import time
        from contextlib import redirect_stdout

        old = self.store.add_plan("Old")
        fresh = self.store.add_plan("Fresh")
        openp = self.store.add_plan("Open")
        services.set_status(self.store, "plan", old.id, Status.DONE)
        services.set_status(self.store, "plan", fresh.id, Status.DONE)
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE events SET ts=? WHERE kind='plan' AND detail LIKE 'plan #1%'",
            (time.time() - 90000,),
        )
        conn.commit()
        conn.close()
        self.assertTrue(services.is_archived(self.store, self.store.get_plan(old.id)))
        self.assertFalse(services.is_archived(self.store, self.store.get_plan(fresh.id)))
        self.assertFalse(services.is_archived(self.store, self.store.get_plan(openp.id)))
        names = [
            p.name
            for p, _ in services.tree(
                self.store,
            )
        ]
        self.assertNotIn("Old", names)
        self.assertIn("Fresh", names)
        self.assertEqual([p.name for p, _ in services.tree(self.store, archived="only")], ["Old"])
        self.assertEqual(len(services.tree(self.store, archived="show")), 3)
        with self.assertRaises(ValueError):
            services.tree(self.store, archived="yesterday")

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
        self.store.add_plan("Todo")
        p2 = self.store.add_plan("Doing")
        p3 = self.store.add_plan("Done")
        services.set_status(self.store, "plan", p2.id, Status.DOING)
        services.set_status(self.store, "plan", p3.id, Status.DONE)
        c = self.store.counts()
        self.assertEqual((c["plans_todo"], c["plans_doing"], c["plans_done"]), (1, 1, 1))
        self.assertEqual(c["plans"], 3)

    def test_removed_verbs_are_gone(self):
        import io
        from contextlib import redirect_stderr

        for argv in (
            ["gantt"],
            ["propose", "--kind", "task", "--parent", "1", "--title", "x"],
            ["ask", "--question", "q"],
            ["sync"],
            ["add-link", "--kind", "task", "--id", "1", "--url", "https://x"],
            ["add-risk", "--plan", "1", "--title", "r"],
            ["add-story", "--project", "1", "--title", "m"],
        ):
            with self.subTest(argv=argv):
                buf = io.StringIO()
                with redirect_stderr(buf):
                    with self.assertRaises(SystemExit) as ctx:
                        lpui_main(["--db", self.db, *argv])
                self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
