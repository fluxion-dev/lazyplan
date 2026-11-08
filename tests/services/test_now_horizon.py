"""Now horizon end-to-end: 20-task apply, context packet, and recipes."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.services import context, plan_apply, plan_document, plan_recipes
from lazyplan.store import Store


def document(tasks: int = 20) -> dict:
    per_milestone = tasks // 2
    milestones = []
    for index in range(2):
        prefix = f"m{index + 1}"
        milestones.append(
            {
                "key": prefix,
                "title": f"Milestone {index + 1}",
                "desc": f"Slice {index + 1} of the work.",
                "tasks": [
                    {
                        "key": f"{prefix}-t{task}",
                        "title": f"Task {index + 1}.{task + 1}",
                        "desc": (
                            "Approach: one reviewable change.\n\n"
                            "Commit: one green slice.\n\n"
                            "Verify: the relevant tests pass."
                        ),
                    }
                    for task in range(per_milestone)
                ],
            }
        )
    return {
        "plan": {
            "key": "now-e2e",
            "title": "Now end-to-end",
            "why": "Prove the loop from one write to one read.",
            "what": "## Scope\n\n- Twenty tasks in two milestones.",
        },
        "milestones": milestones,
    }


class NowHorizonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_twenty_task_apply_is_atomic_and_fast(self):
        parsed = plan_document.validate_document(self.store, document())
        start = time.perf_counter()
        result = plan_apply.apply(self.store, parsed)
        elapsed = time.perf_counter() - start
        self.assertTrue(result["created"])
        self.assertEqual(result["counts"]["tasks"], 20)
        # Windows runners can take 0.15s for the same apply; this still catches
        # a pathological regression without failing on scheduler noise.
        self.assertLess(elapsed, 1.0)
        again = plan_apply.apply(self.store, parsed)
        self.assertFalse(again["created"])
        self.assertEqual(self.store.counts()["tasks"], 20)

    def test_context_resumes_from_the_applied_tree(self):
        parsed = plan_document.validate_document(self.store, document())
        plan_apply.apply(self.store, parsed)
        plan = self.store.get_plan(self.store.get_entity_key("plan", "now-e2e") or 0)
        assert plan is not None
        milestone = self.store.list_milestones(plan.id)[0]
        task = self.store.list_tasks(milestone.id)[0]
        services.set_status(self.store, "task", task.id, Status.DOING, actor="t")
        self.store.claim_task(task.id, "alice", 300)
        payload = context.build(self.store)
        self.assertEqual(payload["plans"][0]["id"], plan.id)
        self.assertEqual(payload["plans"][0]["doing"][0]["id"], task.id)
        self.assertTrue(payload["plans"][0]["next"])

    def test_recipes_are_valid_documents(self):
        for name in plan_recipes.names():
            with self.subTest(recipe=name):
                parsed = plan_document.validate_document(self.store, plan_recipes.load(name))
                self.assertGreaterEqual(len(parsed.milestones[0].tasks), 4)
                self.assertTrue(
                    any("test" in task.title.lower() for task in parsed.milestones[0].tasks)
                )
                self.assertTrue(
                    any("doc" in task.title.lower() for task in parsed.milestones[0].tasks)
                )
                self.assertTrue(
                    any("refactor" in task.title.lower() for task in parsed.milestones[0].tasks)
                )


if __name__ == "__main__":
    unittest.main()
