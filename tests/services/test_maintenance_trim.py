"""Derived-row trim candidates: preview, apply, and live-row safety."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import maintenance
from lazyplan.store import Store

NOW = time.time()
OLD = NOW - 10 * 86400


class TestMaintenanceTrim(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "trim.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan", "what", goal="why")
        self.milestone = self.store.add_milestone(self.plan.id, "Milestone")
        self.expired_task = self.store.add_task(self.milestone.id, "Expired")
        self.live_task = self.store.add_task(self.milestone.id, "Live")
        self.store.add_touchpoint(self.expired_task.id, "src/old.py")
        self.store.add_touchpoint(self.live_task.id, "src/live.py")
        self.store.claim_task(self.expired_task.id, "old", ttl_seconds=60, now=NOW - 1000)
        self.store.claim_task(self.live_task.id, "new", ttl_seconds=10_000, now=NOW)
        self.store.cache_put("old-cache", "e", OLD, "{}")
        self.store.cache_put("new-cache", "e", NOW, "{}")
        self.store.link_forge("task", self.live_task.id, 1, state="open", title="open PR")
        self.store.link_forge("task", self.live_task.id, 2, state="closed", title="closed PR")
        self.store.link_forge("task", self.live_task.id, 3, state="closed", merged_at="2026-01-01")
        self.live_note = self.store.add_note("plan", self.plan.id, "live note")
        self.live_comment = self.store.add_comment("task", self.live_task.id, "live comment")
        self.live_criterion = self.store.add_criteria("plan", self.plan.id, "live criterion")
        self.live_link = self.store.link_commit("task", self.live_task.id, "a" * 40)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _insert_orphans(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text)"
                " VALUES ('plan', 99999, 'x', 1, 'orphan note')"
            )
            conn.execute(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text)"
                " VALUES ('plan', 99999, 'x', 1, 'orphan comment')"
            )
            conn.execute(
                "INSERT INTO criteria (parent_kind, parent_id, text)"
                " VALUES ('plan', 99999, 'orphan criterion')"
            )
            conn.execute(
                "INSERT INTO criterion_links (criterion_id, task_id) VALUES (99998, 99999)"
            )
            conn.execute(
                "INSERT INTO criterion_evidence (criterion_id, task_id, command, ts)"
                " VALUES (99997, 99999, 'pytest', 1)"
            )
            conn.execute(
                "INSERT INTO entity_keys (kind, key, row_id) VALUES ('plan', 'orphan', 99999)"
            )
            conn.execute(
                "INSERT INTO entity_repos (parent_kind, parent_id, repo_path)"
                " VALUES ('plan', 99999, '/tmp/orphan')"
            )
            conn.execute(
                "INSERT INTO issue_links (provider, external_id, row_kind, row_id)"
                " VALUES ('github', 'orphan', 'plan', 99999)"
            )
            conn.execute(
                "INSERT INTO vcs_links (parent_kind, parent_id, sha)"
                f" VALUES ('plan', 99999, '{'f' * 40}')"
            )
            conn.commit()

    def _counts(self, **kwargs) -> dict[str, int]:
        result = maintenance.trim(self.store, now=NOW, days="1", **kwargs)
        return {row.table: row.rows for row in result.tables}

    def _count(self, sql: str) -> int:
        with closing(sqlite3.connect(self.db)) as conn:
            return int(conn.execute(sql).fetchone()[0])

    def test_preview_counts_without_deleting(self) -> None:
        self._insert_orphans()
        counts = self._counts()
        self.assertEqual(counts["task_claims"], 1)
        self.assertEqual(counts["task_touchpoints"], 1)
        self.assertEqual(counts["forge_cache"], 1)
        self.assertEqual(counts["forge_links"], 2)
        self.assertNotIn("notes", counts)
        self.assertNotIn("comments", counts)
        self.assertNotIn("criteria", counts)
        self.assertEqual(counts["criterion_links"], 1)
        self.assertNotIn("criterion_evidence", counts)
        self.assertEqual(counts["entity_keys"], 1)
        self.assertEqual(counts["entity_repos"], 1)
        self.assertEqual(counts["issue_links"], 1)
        self.assertEqual(counts["vcs_links"], 1)
        self.assertEqual(counts["events"], 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM notes"), 2)
        self.assertIsNotNone(self.store.get_claim(self.expired_task.id))

    def test_apply_removes_only_derived_rows(self) -> None:
        self._insert_orphans()
        with closing(sqlite3.connect(self.db)) as conn:
            orphan_notes = tuple(
                row[0]
                for row in conn.execute("SELECT text FROM notes WHERE parent_id=99999 ORDER BY id")
            )
            orphan_comments = tuple(
                row[0]
                for row in conn.execute(
                    "SELECT text FROM comments WHERE parent_id=99999 ORDER BY id"
                )
            )
            orphan_criteria = tuple(
                row[0]
                for row in conn.execute(
                    "SELECT text FROM criteria WHERE parent_id=99999 ORDER BY id"
                )
            )
            orphan_evidence = tuple(
                conn.execute("SELECT command, note FROM criterion_evidence ORDER BY id")
            )
        result = maintenance.trim(self.store, now=NOW, days="1", apply=True)
        self.assertTrue(result.applied)
        counts = {row.table: row.rows for row in result.tables}

        self.assertIsNone(self.store.get_claim(self.expired_task.id))
        self.assertIsNotNone(self.store.get_claim(self.live_task.id))
        self.assertEqual(self.store.list_touchpoints(self.expired_task.id), [])
        self.assertEqual(self.store.list_touchpoints(self.live_task.id), ["src/live.py"])
        self.assertIsNotNone(self.store.cache_get("new-cache"))
        self.assertIsNone(self.store.cache_get("old-cache"))
        states = [link.state for link in self.store.list_forge_links("task", self.live_task.id)]
        self.assertEqual(states, ["open"])

        self.assertEqual(self._count("SELECT COUNT(*) FROM notes"), 2)
        self.assertEqual(self._count("SELECT COUNT(*) FROM comments"), 2)
        self.assertEqual(self._count("SELECT COUNT(*) FROM criteria"), 2)
        self.assertEqual(self._count("SELECT COUNT(*) FROM criterion_links"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM criterion_evidence"), 1)
        self.assertEqual(self._count("SELECT COUNT(*) FROM entity_keys"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM entity_repos"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM issue_links"), 0)
        self.assertEqual(self._count("SELECT COUNT(*) FROM vcs_links"), 1)
        self.assertNotIn("notes", counts)
        self.assertEqual(counts["vcs_links"], 1)

        self.assertEqual(
            [note.text for note in self.store.list_notes("plan", self.plan.id)], ["live note"]
        )
        self.assertEqual(
            [comment.text for comment in self.store.list_comments("task", self.live_task.id)],
            ["live comment"],
        )
        self.assertEqual(
            [row.text for row in self.store.list_criteria("plan", self.plan.id)],
            ["live criterion"],
        )
        self.assertEqual(
            [link.sha for link in self.store.list_links("task", self.live_task.id)],
            [self.live_link.sha],
        )
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                tuple(
                    row[0]
                    for row in conn.execute(
                        "SELECT text FROM notes WHERE parent_id=99999 ORDER BY id"
                    )
                ),
                orphan_notes,
            )
            self.assertEqual(
                tuple(
                    row[0]
                    for row in conn.execute(
                        "SELECT text FROM comments WHERE parent_id=99999 ORDER BY id"
                    )
                ),
                orphan_comments,
            )
            self.assertEqual(
                tuple(
                    row[0]
                    for row in conn.execute(
                        "SELECT text FROM criteria WHERE parent_id=99999 ORDER BY id"
                    )
                ),
                orphan_criteria,
            )
            self.assertEqual(
                tuple(conn.execute("SELECT command, note FROM criterion_evidence ORDER BY id")),
                orphan_evidence,
            )

    def test_old_events_are_trimmed_and_new_events_kept(self) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', 'old')",
                (OLD,),
            )
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'x', 'x', 'new')",
                (NOW,),
            )
            conn.commit()
        counts = self._counts(apply=True)
        self.assertEqual(counts["events"], 1)
        with closing(sqlite3.connect(self.db)) as conn:
            details = {row[0] for row in conn.execute("SELECT detail FROM events")}
        self.assertIn("new", details)
        self.assertNotIn("old", details)

    def test_only_newest_plan_status_event_survives_per_plan(self) -> None:
        plans = [self.store.add_plan(f"Done {index}") for index in range(5)]
        with closing(sqlite3.connect(self.db)) as conn:
            for index in range(50):
                plan = plans[index % len(plans)]
                target = "done" if index >= 45 else ("doing" if index % 2 else "todo")
                conn.execute(
                    "INSERT INTO events (ts, actor, kind, action, detail)"
                    " VALUES (?, 'x', 'plan', 'status', ?)",
                    (OLD + index, f"plan #{plan.id} -> {target}"),
                )
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'x', 'note', 'old non-status')",
                (OLD,),
            )
            conn.commit()
        self.store.set_status_raw("plan", plans[0].id, Status.DONE)

        self._counts(apply=True)

        with closing(sqlite3.connect(self.db)) as conn:
            rows = conn.execute(
                "SELECT substr(detail, 7, instr(substr(detail, 7), ' ') - 1) AS plan_id,"
                " COUNT(*) FROM events WHERE kind='plan' AND action='status'"
                " GROUP BY plan_id"
            ).fetchall()
            non_status = conn.execute(
                "SELECT COUNT(*) FROM events WHERE detail='old non-status'"
            ).fetchone()[0]
        self.assertEqual(len(rows), len(plans))
        self.assertTrue(all(count == 1 for _plan_id, count in rows))
        self.assertEqual(non_status, 0)
        preview = maintenance.archive(self.store, now=NOW, days="1", apply=False)
        self.assertIn(plans[0].id, preview.plans)

    def test_uppercase_status_event_does_not_displace_the_policy_event(self) -> None:
        plan = self.store.add_plan("Case plan")
        self.store.set_status_raw("plan", plan.id, Status.DONE)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'plan', 'status', ?)",
                (OLD, f"plan #{plan.id} -> done"),
            )
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'plan', 'status', ?)",
                (OLD + 1, f"Plan #{plan.id} -> done"),
            )
            conn.commit()

        self._counts(apply=True)

        with closing(sqlite3.connect(self.db)) as conn:
            details = [
                row[0]
                for row in conn.execute(
                    "SELECT detail FROM events WHERE kind='plan' AND action='status'"
                )
            ]
        self.assertEqual(details, [f"plan #{plan.id} -> done"])
        self.assertIn(plan.id, self.store.plan_status_events_map())
        self.assertNotIn(plan.id, [row[0].id for row in services.tree(self.store)])
        preview = maintenance.archive(self.store, now=NOW, days="1", apply=False)
        self.assertIn(plan.id, preview.plans)

    def test_deleted_plan_status_events_are_trimmed(self) -> None:
        plan = self.store.add_plan("Deleted plan")
        self.store.set_status_raw("plan", plan.id, Status.DONE)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'plan', 'status', ?)",
                (OLD, f"plan #{plan.id} -> done"),
            )
            conn.commit()
        self.store.delete("plan", plan.id, actor="fixture")

        self._counts(apply=True)

        with closing(sqlite3.connect(self.db)) as conn:
            kept = conn.execute(
                "SELECT COUNT(*) FROM events WHERE kind='plan' AND action='status' AND detail=?",
                (f"plan #{plan.id} -> done",),
            ).fetchone()[0]
        self.assertEqual(kept, 0)

    def test_status_events_survive_trim_and_keep_the_finished_filter(self) -> None:
        plan = self.store.add_plan("Done old")
        services.set_status(self.store, "plan", plan.id, Status.DONE)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "UPDATE events SET ts=? WHERE detail LIKE ?",
                (OLD, f"plan #{plan.id} -> done%"),
            )
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail)"
                " VALUES (?, 'x', 'x', 'note', 'old non-status')",
                (OLD,),
            )
            conn.commit()

        self._counts(apply=True)

        with closing(sqlite3.connect(self.db)) as conn:
            status_events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE detail LIKE ?",
                (f"plan #{plan.id} -> done%",),
            ).fetchone()[0]
            detail = conn.execute(
                "SELECT COUNT(*) FROM events WHERE detail='old non-status'"
            ).fetchone()[0]
        self.assertEqual(status_events, 1)
        self.assertEqual(detail, 0)
        self.assertNotIn(plan.id, [row[0].id for row in services.tree(self.store)])
        preview = maintenance.archive(self.store, now=NOW, days="1", apply=False)
        self.assertIn(plan.id, preview.plans)


if __name__ == "__main__":
    unittest.main()
