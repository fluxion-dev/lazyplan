"""The `lpui maint` noun group: previews, writes, and exit codes."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.store import Store


class TestMaintenanceCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "maint.db")
        self.store = Store(self.db)
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.old = time.time() - 10 * 86400
        self._seed_old_rows()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_old_rows(self) -> None:
        self.old_plan = self.store.add_plan("Old plan")
        services.set_status(self.store, "plan", self.old_plan.id, Status.DONE)
        self.store.restore_session_history(
            {
                "id": 1,
                "actor": "builder",
                "plan_id": self.old_plan.id,
                "repo_path": self.tmp.name,
                "started_at": self.old,
                "ended_at": self.old,
                "summary": "done",
            }
        )
        self.session_id = 1
        self.store.claim_task(
            self.task.id, "builder", ttl_seconds=60, now=self.old, repo_path=self.tmp.name
        )
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', 'dead')",
                (self.old,),
            )
            conn.execute("UPDATE events SET ts=? WHERE detail LIKE 'plan #% -> done%'", (self.old,))
            conn.commit()

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = lpui_main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def _json(self, *argv: str) -> object:
        code, out, err = self._run("--json", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def _backups(self) -> list[Path]:
        return sorted(Path(self.tmp.name).glob("*.bak-*"))

    def test_help_lists_every_verb(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            lpui_main(["--db", self.db, "maint", "--help"])
        self.assertEqual(caught.exception.code, 0)
        for verb in ("report", "archive", "restore", "trim", "vacuum"):
            self.assertIn(verb, out.getvalue())

    def test_report_json_and_porcelain(self) -> None:
        payload = self._json("maint", "report")
        assert isinstance(payload, dict)
        self.assertIn(payload["method"], ("dbstat", "page_count"))
        self.assertIn("tables", payload)
        self.assertIn("reclaimable_bytes", payload)
        code, out, err = self._run("--porcelain", "maint", "report")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("maint\treport\t"))
        self.assertIn("maint-table\tplans\t", out)

    def test_write_verbs_preview_by_default(self) -> None:
        code, out, err = self._run("--porcelain", "maint", "trim")
        self.assertEqual(code, 0, err)
        self.assertIn("maint-trim\ttask_claims\tpreview\t1", out)
        self.assertIsNotNone(self.store.get_claim(self.task.id))

        code, out, err = self._run("--porcelain", "maint", "archive")
        self.assertEqual(code, 0, err)
        self.assertIn("maint-archive\tplan:", out)
        self.assertIn("maint-archive\tsession:", out)
        self.assertEqual(self._backups(), [])

        code, out, err = self._run("--porcelain", "maint", "vacuum")
        self.assertEqual(code, 0, err)
        self.assertIn("maint-vacuum\tdatabase\tpreview\t", out)
        self.assertEqual(self._backups(), [])

    def test_apply_writes_after_a_snapshot(self) -> None:
        code, out, err = self._run("maint", "trim", "--apply")
        self.assertEqual(code, 0, err)
        self.assertTrue(self._backups())
        self.assertIsNone(self.store.get_claim(self.task.id))
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM events WHERE detail='dead'").fetchone()[0], 0
            )
        self.assertIn("trim", [event["action"] for event in self.store.feed(100)])

    def test_apply_handles_hash_and_question_in_the_path(self) -> None:
        for name in ("hash#name.db", "question?name.db"):
            with self.subTest(name=name):
                if "?" in name and os.name == "nt":
                    self.skipTest("Windows file names cannot contain '?'")
                db = os.path.join(self.tmp.name, name)
                Store(db).add_plan("Path test")
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = lpui_main(["--db", db, "maint", "trim", "--apply"])
                self.assertEqual(code, 0, err)
                self.assertTrue(list(Path(self.tmp.name).glob(f"{name}.bak-*")))

    def test_finished_only_with_archived_show_respects_the_explicit_filter(self) -> None:
        self.store.add_plan("Live plan")
        code, out, err = self._run("list", "--finished", "--archived", "show")
        self.assertEqual(code, 0, err)
        self.assertIn("Old plan", out)
        self.assertNotIn("Live plan", out)

    def test_invalid_window_exits_two_without_a_snapshot(self) -> None:
        code, _out, err = self._run("maint", "trim", "--apply", "--days", "0")
        self.assertEqual(code, 2)
        self.assertIn("window", err)
        self.assertEqual(self._backups(), [])

    def test_restore_returns_a_plan_or_exits_one(self) -> None:
        self.store.archive_plan(self.old_plan.id, actor="builder")
        payload = self._json("maint", "restore", "--plan", str(self.old_plan.id))
        assert isinstance(payload, dict)
        self.assertTrue(payload["restored"])
        row = self.store.get_plan(self.old_plan.id)
        assert row is not None
        self.assertEqual(row.archived_at, 0.0)

        code, _out, err = self._run("maint", "restore", "--plan", "99999")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)


if __name__ == "__main__":
    unittest.main()
