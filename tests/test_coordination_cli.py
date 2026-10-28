"""Claim/next/renew/release CLI behavior and porcelain rows."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from lazyplan import design, services
from lazyplan.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home


class TestCoordinationCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "coordination.db")
        store = Store(self.db)
        plan = store.add_plan("P", "what", goal="why", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T1", description="first", actor="fixture")
        store.add_task(milestone.id, "T2", description="second", actor="fixture")
        self.old_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        sandbox_home(self, self.tmp.name)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"

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

    def _json(self, *argv: str, actor: str = "alice") -> dict:
        code, out, err = self._run("--json", *argv, actor=actor)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_claim_takes_a_lease_and_moves_the_task_doing(self):
        result = self._json("claim", "--id", "1", "--ttl", "30m", "--note", "taking it")
        self.assertEqual(result["claim"]["actor"], "alice")
        self.assertGreater(result["claim"]["expires_at"], result["claim"]["started_at"])
        self.assertEqual(result["task"]["status"], "doing")
        self.assertEqual(Store(self.db).get_task(1).status.value, "doing")

    def test_claim_conflict_reports_the_holder(self):
        self._json("claim", "--id", "1")
        code, out, err = self._run("claim", "--id", "1", actor="bob")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("alice", err)
        self.assertIn("claimed", err)

    def test_force_takeover_records_the_previous_holder(self):
        self._json("claim", "--id", "1")
        result = self._json("claim", "--id", "1", "--force", actor="bob")
        self.assertEqual(result["claim"]["actor"], "bob")
        self.assertEqual(result["previous"]["actor"], "alice")

    def test_renew_requires_the_holder(self):
        before = self._json("claim", "--id", "1", "--ttl", "30m")
        after = self._json("claim", "renew", "--id", "1", "--ttl", "1.hours")
        self.assertGreater(after["claim"]["expires_at"], before["claim"]["expires_at"])
        code, _, err = self._run("claim", "renew", "--id", "1", actor="bob")
        self.assertEqual(code, 1)
        self.assertIn("held by another actor", err)

    def test_release_and_missing_release(self):
        self._json("claim", "--id", "1")
        result = self._json("claim", "release", "--id", "1")
        self.assertEqual(result["claim"]["actor"], "alice")
        self.assertIsNone(Store(self.db).get_claim(1))
        code, out, err = self._run("claim", "release", "--id", "1")
        self.assertEqual(code, 0)
        self.assertIn("was not claimed", out)

    def test_next_claims_first_todo_then_the_second(self):
        first = self._json("next")
        self.assertEqual(first["task"]["id"], 1)
        self.assertEqual(first["task"]["status"], "doing")
        second = self._json("next")
        self.assertEqual(second["task"]["id"], 2)
        self.assertIsNone(self._json("next"))

    def test_next_suggest_does_not_claim(self):
        result = self._json("next", "--suggest")
        self.assertEqual(result["task"]["id"], 1)
        self.assertEqual(result["task"]["status"], "todo")
        self.assertIsNone(result["claim"])
        self.assertIsNone(Store(self.db).get_claim(1))

    def test_next_skips_a_claimed_task(self):
        self._json("claim", "--id", "1")
        result = self._json("next")
        self.assertEqual(result["task"]["id"], 2)

    def test_claim_rows_in_porcelain(self):
        code, out, err = self._run("--porcelain", "claim", "--id", "1")
        self.assertEqual(code, 0, err)
        row = out.rstrip("\n").split("\t")
        self.assertEqual(row[:5], ["claim", "1", "alice", "T1", "task:1"])
        self.assertTrue(float(row[5]) > 0)

        code, out, err = self._run("--porcelain", "claims")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\t")[:5], row[:5])

        code, out, err = self._run("--porcelain", "next")
        self.assertEqual(code, 0, err)
        self.assertEqual(
            out.rstrip("\n").split("\t"), ["task", "2", "doing", "T2", "milestone:1", "-"]
        )

    def test_release_porcelain_has_no_expiry(self):
        self._json("claim", "--id", "1")
        code, out, err = self._run("--porcelain", "claim", "release", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\t"), ["claim", "1", "alice", "T1", "task:1", "-"])

    def test_who_alias_lists_claims(self):
        self._json("claim", "--id", "1")
        code, out, err = self._run("who")
        self.assertEqual(code, 0, err)
        self.assertIn("T1", out)
        self.assertIn("@alice", out)

    def test_claim_appears_in_show_brief_and_tree(self):
        self._json("claim", "--id", "1")
        code, out, err = self._run("--porcelain", "task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        rows = [line.split("\t") for line in out.rstrip("\n").splitlines()]
        self.assertIn(["claim", "1", "alice", "T1", "task:1", rows[1][5]], rows)

        code, out, err = self._run("--porcelain", "plan", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("claim\t1\talice\tT1\ttask:1\t", out)
        code, out, err = self._run("--porcelain", "brief", "--plan", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("claim\t1\talice\tT1\ttask:1\t", out)

        payload = self._json("brief", "--plan", "1")
        self.assertEqual(payload["plans"][0]["doing"][0]["claim"]["actor"], "alice")
        code, out, err = self._run("task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("claim: @alice", out)

        store = Store(self.db)
        self.assertIn("@alice", design.task_label(store.get_task(1), store))
        self.assertIn("@alice", design.task_row(store.get_task(1), claim_actor="alice"))

    def test_ttl_parser(self):
        self.assertEqual(services.parse_ttl("30m"), 1800)
        self.assertEqual(services.parse_ttl("2.hours"), 7200)
        self.assertEqual(services.parse_ttl("90"), 90)
        self.assertEqual(services.parse_ttl("1.days"), 86400)
        with self.assertRaises(ValueError):
            services.parse_ttl("soon")


if __name__ == "__main__":
    unittest.main()
