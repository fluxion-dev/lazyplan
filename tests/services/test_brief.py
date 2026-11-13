"""Session brief: active plan, next task, criteria, and loose commits."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from lazyplan.services import audit, brief
from lazyplan.store import Store
from tests.support.home import sandbox_home


class BriefCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "lazyplan.db")
        self.plan = self.store.add_plan("P", "what", goal="why")
        self.milestone = self.store.add_milestone(self.plan.id, "M", "desc")
        self.doing = self.store.add_task(self.milestone.id, "Doing task", "desc")
        self.next_task = self.store.add_task(self.milestone.id, "Next task", "desc")
        services.set_status(self.store, "task", self.doing.id, Status.DOING, actor="t")
        services.set_status(self.store, "milestone", self.milestone.id, Status.DOING, actor="t")
        services.set_status(self.store, "plan", self.plan.id, Status.DOING, actor="t")
        self.store.add_criteria("task", self.doing.id, "still open")

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_names_doing_next_criteria_and_loose_commits(self):
        self.store.link_commit(
            "task", self.doing.id, "a" * 40, subject="linked", timestamp=1000, actor="t"
        )
        commits = [
            audit.Commit("a" * 40, 1000, "/r", 1, "linked"),
            audit.Commit("b" * 40, 1100, "/r", 1, "loose"),
        ]
        payload = brief.build(self.store, commits=commits)
        plan = payload["plans"][0]
        self.assertEqual(plan["doing"][0]["title"], "Doing task")
        self.assertEqual(plan["next"]["title"], "Next task")
        self.assertEqual(plan["criteria"][0]["text"], "still open")
        self.assertEqual([item["subject"] for item in plan["unlinked"]], ["loose"])

    def test_text_lists_the_same_facts(self):
        text = "\n".join(brief.lines(brief.build(self.store, commits=[])))
        self.assertIn("Doing task", text)
        self.assertIn("Next task", text)
        self.assertIn("open criteria", text)

    def test_approval_and_drift_are_in_brief(self):
        self.store.add_revision(self.plan.id, "a" * 64, "{}")
        self.store.update_task(self.doing.id, title="Renamed", reason="rename")
        payload = brief.build(self.store, commits=[])
        approval = payload["plans"][0]["approval"]
        self.assertEqual(approval["revision"], 1)
        self.assertEqual(approval["drift"], 1)
        text = "\n".join(brief.lines(payload))
        self.assertIn("drift", text)
        self.assertIn("r1", text)

    def test_approval_in_sync_is_in_brief(self):
        self.store.add_revision(self.plan.id, "a" * 64, "{}")
        payload = brief.build(self.store, commits=[])
        self.assertEqual(payload["plans"][0]["approval"]["drift"], 0)
        self.assertIn("approval r1 in sync", "\n".join(brief.lines(payload)))

    def test_open_questions_are_in_brief(self):
        question = self.store.add_question(self.plan.id, "Which host?")
        payload = brief.build(self.store, commits=[])
        self.assertEqual(payload["plans"][0]["questions"][0]["id"], question.id)
        text = "\n".join(brief.lines(payload))
        self.assertIn("questions 1 open", text)
        self.assertIn("Which host?", text)

    def test_previous_session_handoff_is_in_brief(self):
        agent = self.store.add_agent(
            "alice", host="opencode", agent="alice", plan_id=self.plan.id, now=100.0
        )
        self.store.end_agent(agent.id, "alice", summary="shipped", handoff="next: T2", now=200.0)
        payload = brief.build(self.store, commits=[])
        self.assertEqual(payload["plans"][0]["previous_session"]["handoff"], "next: T2")
        text = "\n".join(brief.lines(payload))
        self.assertIn("session  A", text)
        self.assertIn("next: T2", text)

    def test_empty_store_says_no_active_plans(self):
        empty = Store(Path(self.tmp.name) / "empty.db")
        self.assertEqual(brief.lines(brief.build(empty, commits=[])), ["no active plans"])

    def test_done_plan_is_not_active(self):
        services.set_status(self.store, "task", self.doing.id, Status.DONE, actor="t")
        services.set_status(self.store, "task", self.next_task.id, Status.DONE, actor="t")
        services.set_status(self.store, "milestone", self.milestone.id, Status.DONE, actor="t")
        services.set_status(self.store, "plan", self.plan.id, Status.DONE, actor="t")
        self.assertEqual(brief.build(self.store, commits=[])["plans"], [])


class BriefCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(argv)
        return code, out.getvalue()

    def test_missing_database_is_empty_and_file_free(self):
        code, out = self._run(["brief", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["plans"], [])
        self.assertFalse((self.home / ".lazyplan").exists())

    def test_json_reports_active_plan(self):
        store = Store(self.home / ".lazyplan/lazyplan.db")
        plan = store.add_plan("P", "what", goal="why")
        milestone = store.add_milestone(plan.id, "M", "desc")
        task = store.add_task(milestone.id, "T", "desc")
        services.set_status(store, "task", task.id, Status.DOING, actor="t")
        services.set_status(store, "milestone", milestone.id, Status.DOING, actor="t")
        services.set_status(store, "plan", plan.id, Status.DOING, actor="t")
        code, out = self._run(["brief", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["plans"][0]["id"], plan.id)


if __name__ == "__main__":
    unittest.main()
