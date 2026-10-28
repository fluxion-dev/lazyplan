"""Noun-first CLI: canonical groups, legacy aliases, and text output."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from lazyplan.cli import main as lpui_main
from lazyplan.store import Store


class TestNounFirstCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = lpui_main(["--db", self.db, *argv])
        return code, buf.getvalue()

    def _json(self, *argv: str) -> object:
        code, out = self._run("--json", *argv)
        self.assertEqual(code, 0)
        return json.loads(out)

    def test_plan_lifecycle(self):
        plan = self._json("plan", "add", "--title", "P", "--why", "why", "--what", "what")
        assert isinstance(plan, dict)
        pid = plan["plan"]["id"]
        summary = self._run("plan", "list")[1]
        self.assertIn(f"P{pid} P", summary)
        self.assertIn("0/0", summary)
        self._run("plan", "edit", "--id", str(pid), "--title", "P2")
        self.assertEqual(Store(self.db).get_plan(pid).name, "P2")
        self._run("plan", "move", "--id", str(pid), "--to", "doing")
        self.assertEqual(Store(self.db).get_plan(pid).status.value, "doing")
        self._run("plan", "delete", "--id", str(pid))
        self.assertIsNone(Store(self.db).get_plan(pid))

    def test_milestone_and_task_groups(self):
        pid = self.store.add_plan("P").id
        ms = self._json("milestone", "add", "--plan", str(pid), "--title", "M", "--desc", "d")
        assert isinstance(ms, dict)
        sid = ms["milestone"]["id"]
        task = self._json("task", "add", "--milestone", str(sid), "--title", "T", "--desc", "d")
        assert isinstance(task, dict)
        tid = task["task"]["id"]
        self._run("task", "move", "--id", str(tid), "--to", "doing")
        self.assertEqual(Store(self.db).get_task(tid).status.value, "doing")
        tree = self._run("milestone", "list", "--plan", str(pid))[1]
        self.assertIn("M", tree)
        self.assertIn("T", tree)
        tasks = self._run("task", "list", "--milestone", str(sid))[1]
        self.assertIn("T", tasks)

    def test_criterion_group(self):
        pid = self.store.add_plan("P").id
        c = self._json("criterion", "add", "--kind", "plan", "--id", str(pid), "--text", "works")
        assert isinstance(c, dict)
        cid = c["criteria"]["id"]
        self._run("criterion", "tick", "--id", str(cid))
        self.assertTrue(Store(self.db).list_criteria("plan", pid)[0].done)
        self._run("criterion", "untick", "--id", str(cid))
        self.assertFalse(Store(self.db).list_criteria("plan", pid)[0].done)
        self.assertIn(
            "works", self._run("criterion", "list", "--kind", "plan", "--id", str(pid))[1]
        )
        self._run("criterion", "delete", "--id", str(cid))
        self.assertEqual(Store(self.db).list_criteria("plan", pid), [])

    def test_list_is_summary_first_and_tree_is_opt_in(self):
        pid = self.store.add_plan("P").id
        sid = self.store.add_milestone(pid, "M").id
        self.store.add_task(sid, "T")
        summary = self._run("list")[1]
        self.assertIn("P", summary)
        self.assertIn("/1", summary)
        self.assertNotIn("T", summary)
        tree = self._run("list", "--tree")[1]
        self.assertIn("M", tree)
        self.assertIn("T", tree)

    def test_legacy_aliases_still_work(self):
        out = self._json("add-plan", "--title", "Legacy", "--why", "w", "--what", "x")
        assert isinstance(out, dict)
        pid = out["plan"]["id"]
        self.assertEqual(Store(self.db).get_plan(pid).name, "Legacy")
        code, text = self._run("show", "--kind", "plan", "--id", str(pid))
        self.assertEqual(code, 0)
        self.assertIn(f"P{pid} Legacy", text)
        self.assertNotIn("#", text)

    def test_json_shape_is_unchanged(self):
        pid = self.store.add_plan("P").id
        self.store.add_milestone(pid, "M")
        payload = self._json("list")
        assert isinstance(payload, list)
        self.assertIn("plan", payload[0])
        self.assertIn("milestones", payload[0])


if __name__ == "__main__":
    unittest.main()
