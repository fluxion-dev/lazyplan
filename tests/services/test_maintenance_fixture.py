"""Trim safety and space reclaim on a fixture dense with dead rows."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing

from lazyplan.services import maintenance
from lazyplan.store import Store


class TestMaintenanceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "fixture.db")
        self.store = Store(self.db)
        self.now = time.time()
        self.old = self.now - 10 * 86400
        self._build()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _build(self) -> None:
        self.plan = self.store.add_plan("Live plan text", "live what " * 40, goal="live why " * 40)
        self.milestone = self.store.add_milestone(
            self.plan.id, "Live milestone text", "live milestone detail " * 40
        )
        self.task = self.store.add_task(
            self.milestone.id, "Live task text", "live task detail " * 40
        )
        self.note = self.store.add_note("plan", self.plan.id, "live note text " * 40)
        self.comment = self.store.add_comment("task", self.task.id, "live comment text " * 40)
        self.criterion = self.store.add_criteria("plan", self.plan.id, "live criterion text " * 40)
        self.dead_tasks = [
            self.store.add_task(self.milestone.id, f"Dead task {index:03d}", "dead detail")
            for index in range(40)
        ]
        with closing(sqlite3.connect(self.db)) as conn:
            conn.executemany(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', ?)",
                [(self.old, "dead event " + "x" * 300) for _ in range(6_000)]
                + [(self.now, "live event " + "x" * 300) for _ in range(5)],
            )
            conn.executemany(
                "INSERT INTO task_claims (task_id, actor, started_at, expires_at)"
                " VALUES (?, 'x', ?, ?)",
                [(task.id, self.old, self.old + 60) for task in self.dead_tasks],
            )
            conn.executemany(
                "INSERT INTO task_touchpoints (task_id, pattern) VALUES (?, 'src/dead.py')",
                [(task.id,) for task in self.dead_tasks],
            )
            conn.executemany(
                "INSERT INTO forge_cache (key, etag, fetched_at, payload) VALUES (?, 'e', ?, ?)",
                [(f"old-{index}", self.old, "cache " * 200) for index in range(500)],
            )
            conn.executemany(
                "INSERT INTO forge_links"
                " (parent_kind, parent_id, provider, kind, number, state, title, payload)"
                " VALUES ('task', ?, 'github', 'pull', ?, 'closed', 'dead PR', ?)",
                [(self.task.id, 1_000 + index, "payload " * 100) for index in range(100)],
            )
            conn.executemany(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text)"
                " VALUES ('plan', 999999, 'x', ?, ?)",
                [(self.old, f"orphan note {index} " + "x" * 500) for index in range(100)],
            )
            conn.executemany(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text)"
                " VALUES ('task', 999999, 'x', ?, ?)",
                [(self.old, f"orphan comment {index} " + "x" * 500) for index in range(100)],
            )
            conn.executemany(
                "INSERT INTO criteria (parent_kind, parent_id, text) VALUES ('plan', 999999, ?)",
                [(f"orphan criterion {index} " + "x" * 500,) for index in range(100)],
            )
            conn.executemany(
                "INSERT INTO entity_repos (parent_kind, parent_id, repo_path)"
                " VALUES ('plan', ?, '/tmp/orphan')",
                [(999_900 + index,) for index in range(40)],
            )
            conn.executemany(
                "INSERT INTO issue_links (provider, external_id, row_kind, row_id)"
                " VALUES ('github', ?, 'plan', ?)",
                [(f"orphan-{index}", 999_900 + index) for index in range(40)],
            )
            conn.executemany(
                "INSERT INTO vcs_links (parent_kind, parent_id, sha, subject)"
                " VALUES ('plan', ?, ?, 'orphan commit')",
                [(999_900 + index, f"{index:040x}") for index in range(40)],
            )
            conn.executemany(
                "INSERT INTO entity_keys (kind, key, row_id) VALUES ('plan', ?, ?)",
                [(f"orphan-{index}", 999_900 + index) for index in range(40)],
            )
            conn.executemany(
                "INSERT INTO criterion_links (criterion_id, task_id) VALUES (?, 999999)",
                [(999_900 + index,) for index in range(40)],
            )
            conn.commit()

    def _texts(self) -> tuple:
        with closing(sqlite3.connect(self.db)) as conn:
            return (
                conn.execute(
                    "SELECT name, description, goal FROM plans WHERE id=?", (self.plan.id,)
                ).fetchone(),
                conn.execute(
                    "SELECT title, description FROM milestones WHERE id=?", (self.milestone.id,)
                ).fetchone(),
                conn.execute(
                    "SELECT title, description FROM tasks WHERE id=?", (self.task.id,)
                ).fetchone(),
                conn.execute("SELECT text FROM notes WHERE id=?", (self.note.id,)).fetchone(),
                conn.execute("SELECT text FROM comments WHERE id=?", (self.comment.id,)).fetchone(),
                conn.execute(
                    "SELECT text FROM criteria WHERE id=?", (self.criterion.id,)
                ).fetchone(),
            )

    def test_trim_vacuum_preserve_user_text_and_reclaim_space(self) -> None:
        before_text = self._texts()
        before_size = os.path.getsize(self.db)
        predicted = maintenance.report(self.store).reclaimable_bytes

        maintenance.trim(self.store, days="1", apply=True)
        maintenance.vacuum(self.store, apply=True)

        after_size = os.path.getsize(self.db)
        measured = before_size - after_size
        self.assertGreater(measured, 0)
        self.assertGreater(predicted, 0)
        self.assertLessEqual(abs(predicted - measured), 0.10 * measured)
        self.assertEqual(self._texts(), before_text)

        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM notes WHERE parent_id=999999").fetchone()[0],
                100,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE detail LIKE 'dead event %'"
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE detail LIKE 'live event %'"
                ).fetchone()[0],
                5,
            )


if __name__ == "__main__":
    unittest.main()
