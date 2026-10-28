"""Review comments: add/list/resolve, mentions, and parent cleanup."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.cli import main as lpui_main
from lazyplan.store import Store
from tests.support.home import sandbox_home


class TestComments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "comments.db")
        store = Store(self.db)
        plan = store.add_plan("P", actor="fixture")
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        store.add_task(milestone.id, "T", actor="fixture")
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

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = lpui_main(["--db", self.db, "--actor", "alice", *argv])
        return code, out.getvalue(), err.getvalue()

    def _json(self, *argv: str) -> object:
        code, out, err = self._run("--json", *argv)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_add_list_and_mention_filter(self):
        self._json("comment", "add", "--kind", "task", "--id", "1", "--text", "ping @bob")
        self._json("comment", "add", "--kind", "task", "--id", "1", "--text", "no mention")
        listed = self._json("comment", "list", "--kind", "task", "--id", "1")
        self.assertEqual(len(listed), 2)
        mentions = self._json("comment", "list", "--kind", "task", "--id", "1", "--mentions", "bob")
        self.assertEqual([item["text"] for item in mentions], ["ping @bob"])

    def test_resolve_and_unresolve(self):
        created = self._json("comment", "add", "--kind", "task", "--id", "1", "--text", "fix")
        cid = created["comment"]["id"]
        resolved = self._json("comment", "resolve", "--comment", str(cid))
        self.assertTrue(resolved["comment"]["resolved"])
        reopened = self._json("comment", "unresolve", "--comment", str(cid))
        self.assertFalse(reopened["comment"]["resolved"])

    def test_porcelain(self):
        code, out, err = self._run(
            "--porcelain", "comment", "add", "--kind", "task", "--id", "1", "--text", "hi"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\t")[:5], ["comment", "1", "open", "hi", "task:1"])
        code, out, err = self._run("--porcelain", "comment", "resolve", "--comment", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n").split("\t")[:3], ["comment", "1", "resolved"])

    def test_show_brief_and_export(self):
        self._json("comment", "add", "--kind", "task", "--id", "1", "--text", "review this")
        code, out, err = self._run("task", "show", "--id", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("review this", out)
        code, out, err = self._run("--porcelain", "task", "show", "--id", "1")
        self.assertIn("comment\t1\topen\treview this\ttask:1\t", out)
        self._json("claim", "--id", "1")
        brief = self._json("brief", "--plan", "1")
        self.assertEqual(brief["plans"][0]["doing"][0]["comments"][0]["text"], "review this")
        data = services.export_all(Store(self.db))
        self.assertEqual(
            data["plans"][0]["milestones"][0]["tasks"][0]["comments"][0]["text"], "review this"
        )
        other = Store(os.path.join(self.tmp.name, "other.db"))
        counts = services.import_all(other, data, actor="fixture")
        self.assertEqual(counts["comments"], 1)
        self.assertEqual(other.list_comments("task", 1)[0].text, "review this")

    def test_deleting_parent_removes_comments(self):
        store = Store(self.db)
        store.add_comment("task", 1, "gone", actor="fixture")
        store.delete("task", 1)
        self.assertEqual(store.list_comments("task", 1), [])

    def test_missing_parent_is_an_error(self):
        code, out, err = self._run("comment", "add", "--kind", "task", "--id", "99", "--text", "x")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_resolve_needs_comment_id(self):
        code, out, err = self._run("comment", "resolve")
        self.assertEqual(code, 2)
        self.assertIn("--comment", err)


if __name__ == "__main__":
    unittest.main()
