"""Collaboration QA: comments, share escaping, UID sync, and conflicts."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import services, share, sync  # noqa: E402
from lazyplan.store import Store  # noqa: E402


class TestCollaborationQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Store(os.path.join(self.tmp.name, "source.db"))
        plan = self.source.add_plan("Plan <unsafe>", "what & why", goal="because", actor="qa")
        milestone = self.source.add_milestone(plan.id, "M", actor="qa")
        task = self.source.add_task(milestone.id, "T", actor="qa")
        self.source.add_comment("task", task.id, "ping @alice <b>", actor="qa")
        self.source.add_note("plan", plan.id, "note", actor="qa")
        self.target = Store(os.path.join(self.tmp.name, "target.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_comment_share_and_sync_together(self):
        comment = self.source.list_comments("task", 1, mentions="alice")[0]
        self.source.resolve_comment(comment.id, True, actor="qa")
        self.assertTrue(self.source.list_comments("task", 1)[0].resolved)

        html = share.render_html(self.source, 1)
        assert html is not None
        self.assertIn("&lt;unsafe&gt;", html)
        self.assertIn("&lt;b&gt;", html)
        self.assertIn("because", html)
        data = json.loads(share.render_json(self.source, 1) or "{}")
        self.assertEqual(data["plan"]["id"], 1)

        dump = services.export_all(self.source)
        first = sync.sync(self.target, dump, actor="qa")
        self.assertEqual(len(first["added"]), 1)
        second = sync.sync(self.target, dump, actor="qa")
        self.assertEqual(len(second["skipped"]), 1)
        self.assertEqual(len(self.target.list_plans()), 1)
        self.assertEqual(self.target.list_comments("task", 1)[0].text, "ping @alice <b>")

    def test_conflict_and_dry_run(self):
        dump = services.export_all(self.source)
        sync.sync(self.target, dump, actor="qa")
        dry = sync.sync(self.target, dump, actor="qa", dry_run=True)
        self.assertEqual(len(dry["skipped"]), 1)
        dump["plans"][0]["plan"]["name"] = "Different"
        conflict = sync.sync(self.target, dump, actor="qa")
        self.assertEqual(len(conflict["conflicts"]), 1)
        self.assertEqual(self.target.get_plan(1).name, "Plan <unsafe>")


if __name__ == "__main__":
    unittest.main()
