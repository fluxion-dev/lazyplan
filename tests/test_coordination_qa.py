"""Coordination under real concurrent processes, plus handoff/blocked flow."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from support.home import sandbox_home  # noqa: E402

from lazyplan.cli import main as lpui_main  # noqa: E402
from lazyplan.store import Store  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCoordinationQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "qa.db")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T1", description="first", actor="fixture")
        store.add_task(milestone.id, "T2", description="second", actor="fixture")

    def tearDown(self):
        for key, value in (("LAZYPLAN_NO_SETUP", self.old_setup),):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, *argv: str, actor: str = "alice") -> tuple[int, str, str]:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", actor, *argv])
        return code, out.getvalue(), err.getvalue()

    def _json(self, *argv: str, actor: str = "alice") -> object:
        code, out, err = self._run("--json", *argv, actor=actor)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def _race_next(self, count: int) -> list[dict]:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src")
        env["LAZYPLAN_NO_SETUP"] = "1"
        procs = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lazyplan",
                    "--db",
                    self.db,
                    "--actor",
                    f"agent{i}",
                    "--json",
                    "next",
                ],
                cwd=self.tmp.name,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
            for i in range(count)
        ]
        winners = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err)
            payload = json.loads(out)
            if payload is not None:
                winners.append(payload)
        return winners

    def test_concurrent_next_has_one_winner_per_task(self):
        winners = self._race_next(100)
        self.assertEqual(len(winners), 2)
        self.assertEqual({winner["task"]["id"] for winner in winners}, {1, 2})
        store = Store(self.db)
        for winner in winners:
            claim = store.get_claim(winner["task"]["id"])
            assert claim is not None
            self.assertEqual(claim.actor, winner["claim"]["actor"])
            self.assertEqual(store.get_task(winner["task"]["id"]).status.value, "doing")

    def test_expired_claim_is_reclaimed_by_next(self):
        store = Store(self.db)
        store.claim_task(1, "stale", ttl_seconds=1, now=1)
        result = self._json("next")
        self.assertEqual(result["task"]["id"], 1)
        self.assertEqual(result["claim"]["actor"], "alice")

    def test_force_takeover_and_handoff_note(self):
        self._json("claim", "--id", "1", actor="alice")
        self._json("note", "add", "--kind", "task", "--id", "1", "--text", "handoff")
        result = self._json("claim", "--id", "1", "--force", actor="bob")
        self.assertEqual(result["claim"]["actor"], "bob")
        self.assertEqual(result["previous"]["actor"], "alice")
        self.assertEqual(Store(self.db).list_notes("task", 1)[0].text, "handoff")

    def test_block_unblock_flow_skips_and_restores(self):
        self._json("task", "block", "--id", "1", "--reason", "waiting on design")
        result = self._json("next")
        self.assertEqual(result["task"]["id"], 2)
        self._json("task", "unblock", "--id", "1")
        self.assertEqual(self._json("next")["task"]["id"], 1)

    def test_porcelain_loop_from_next_to_audit(self):
        code, out, err = self._run("--porcelain", "next")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.rstrip("\n").split("\t")[:5], ["task", "1", "doing", "T1", "milestone:1"]
        )
        code, out, err = self._run("--porcelain", "claims")
        self.assertEqual(code, 0, err)
        self.assertIn("claim\t1\talice\tT1\ttask:1\t", out)
        code, out, err = self._run(
            "--porcelain", "note", "add", "--kind", "task", "--id", "1", "--text", "handoff"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("note\t1\talice\thandoff\ttask:1\t", out)
        code, out, err = self._run("--porcelain", "task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("claim\t1\talice\tT1\ttask:1\t", out)
        self.assertIn("handoff", out)
        code, out, err = self._run("--porcelain", "audit", "--plan", "1", "--since", "2026-01-01")
        self.assertEqual(code, 0, err)
        self.assertIn("metric\tplans\t-\tP1", out)


if __name__ == "__main__":
    unittest.main()
