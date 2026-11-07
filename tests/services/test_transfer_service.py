"""Transfer use cases over the transfer port."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.store import Store


class TestTransferService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "transfer.db"))
        plan = self.store.add_plan("P", "what", goal="why", actor="fixture")
        self.store.add_criteria("plan", plan.id, "works", actor="fixture")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_export_import_round_trip(self) -> None:
        dump = services.export_all(self.store)
        self.assertEqual(dump["lazyplan"], 1)
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["plans"], 1)
            self.assertEqual(target.list_plans()[0].name, "P")

    def test_share_payload_is_redacted(self) -> None:
        plan_id = self.store.list_plans()[0].id
        self.assertIn("plan", services.export_plan(self.store, plan_id))

    def test_export_import_carries_evidence(self) -> None:
        plan = self.store.list_plans()[0]
        milestone = self.store.add_milestone(plan.id, "M", actor="fixture")
        task = self.store.add_task(milestone.id, "T", actor="fixture")
        criterion = self.store.add_criteria("task", task.id, "Works", actor="fixture")
        self.store.relate_criterion(criterion.id, task.id, actor="fixture")
        self.store.add_evidence(
            criterion.id,
            command="pytest",
            exit_code=0,
            commit_sha="a" * 40,
            task_id=task.id,
            actor="ci",
        )
        dump = services.export_all(self.store)
        exported = dump["plans"][0]["milestones"][0]["tasks"][0]["criteria"][0]["evidence"][0]
        self.assertEqual(exported["command"], "pytest")
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["evidence"], 1)
            target_plan = target.list_plans()[0]
            target_milestone = target.list_milestones(target_plan.id)[0]
            target_task = target.list_tasks(target_milestone.id)[0]
            target_criterion = target.list_criteria("task", target_task.id)[0]
            rows = target.list_evidence(target_criterion.id)
            self.assertEqual(rows[0].command, "pytest")
            self.assertEqual(rows[0].actor, "ci")
            self.assertEqual(rows[0].task_id, target_task.id)

    def test_export_import_carries_questions(self) -> None:
        plan = self.store.list_plans()[0]
        question = self.store.add_question(plan.id, "Which host?", actor="qa")
        self.store.resolve_question(question.id, "OpenCode", actor="human")
        dump = services.export_all(self.store)
        exported = dump["plans"][0]["questions"][0]
        self.assertEqual(exported["status"], "resolved")
        self.assertEqual(exported["resolution"], "OpenCode")
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["questions"], 1)
            target_plan = target.list_plans()[0]
            restored = target.list_questions(target_plan.id, status="all")[0]
            self.assertEqual(restored.text, "Which host?")
            self.assertEqual(restored.status, "resolved")
            self.assertEqual(restored.resolution, "OpenCode")
            self.assertEqual(restored.actor, "qa")

    def test_export_import_carries_refs(self) -> None:
        plan = self.store.list_plans()[0]
        ref = self.store.link_ref(
            plan.id,
            "https://github.com/o/r/issues/7",
            title="Epic",
            state="open",
            actor="qa",
        )
        dump = services.export_all(self.store)
        exported = dump["plans"][0]["refs"][0]
        self.assertEqual(exported["url"], ref.url)
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["refs"], 1)
            target_plan = target.list_plans()[0]
            restored = target.list_refs(target_plan.id)[0]
            self.assertEqual(restored.url, ref.url)
            self.assertEqual(restored.title, "Epic")
            self.assertEqual(restored.state, "open")

    def test_import_tolerates_missing_evidence_task(self) -> None:
        plan = self.store.list_plans()[0]
        criterion = self.store.list_criteria("plan", plan.id)[0]
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0)
        dump = services.export_all(self.store)
        dump["plans"][0]["criteria"][0]["evidence"][0]["task_id"] = 999
        with tempfile.TemporaryDirectory() as other:
            target = Store(os.path.join(other, "target.db"))
            counts = services.import_all(target, dump, actor="fixture")
            self.assertEqual(counts["evidence"], 1)
            target_plan = target.list_plans()[0]
            target_criterion = target.list_criteria("plan", target_plan.id)[0]
            self.assertIsNone(target.list_evidence(target_criterion.id)[0].task_id)


if __name__ == "__main__":
    unittest.main()
