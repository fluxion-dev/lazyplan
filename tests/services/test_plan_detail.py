"""Resume-contract validation for plan milestones and tasks."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.services import draft_sketch, plan_apply, plan_detail, plan_document
from lazyplan.store import Store

MILESTONE = (
    "Outcome: As a user, I want the change, so that the outcome is visible.\n\n"
    "Scope: In scope: the reviewed definition. Out of scope: unrelated work.\n\n"
    "Inputs: The approved definition and the scouted code path.\n\n"
    "Slices: Implement and verify in separate green commits."
)

TASK = (
    "Approach: Change the scouted code path and keep the reviewed behavior.\n\n"
    "Touch: src/app.py, tests/test_app.py\n\n"
    "Inputs: The approved definition; none beyond the plan scope.\n\n"
    "Commit: One implementation slice.\n\n"
    "Verify: The relevant test suite passes.\n\n"
    "Guardrails: Keep behavior outside the reviewed scope unchanged."
)

SKETCH = """# Draft title

## Why

Because review should stay at the definition.

## What

## Scope

- One slice.

## Done

- Works.
"""


def document(task_desc: str = TASK, milestone_desc: str = MILESTONE) -> dict:
    """One valid plan document with optional shallow descriptions."""
    return {
        "plan": {
            "key": "resume-contract",
            "title": "Draft title",
            "why": "Because review should stay at the definition.",
            "what": "## Scope\n\n- One slice.",
            "criteria": ["Works."],
        },
        "milestones": [
            {
                "key": "slice",
                "title": "Deliver the slice",
                "desc": milestone_desc,
                "tasks": [
                    {
                        "key": "impl",
                        "title": "Implement the slice",
                        "desc": task_desc,
                    }
                ],
            }
        ],
    }


class PlanDetailTest(unittest.TestCase):
    def test_complete_descriptions_have_no_issues(self) -> None:
        self.assertEqual(plan_detail.milestone_issues(MILESTONE), [])
        self.assertEqual(plan_detail.task_issues(TASK), [])

    def test_missing_sections_are_named(self) -> None:
        issues = plan_detail.task_issues("Approach: do the work.")
        self.assertEqual(
            [issue.section for issue in issues],
            ["Touch", "Inputs", "Commit", "Verify", "Guardrails"],
        )
        self.assertEqual(
            plan_detail.describe(issues),
            "Touch, Inputs, Commit, Verify and Guardrails are missing",
        )
        milestone_issues = plan_detail.milestone_issues("As a user, I want it.")
        self.assertEqual(
            [issue.section for issue in milestone_issues],
            ["Outcome", "Scope", "Inputs", "Slices"],
        )

    def test_aliases_and_headings_are_accepted(self) -> None:
        task = (
            "How: Change the scouted path.\n\n"
            "Files: src/app.py\n\n"
            "Prerequisites: The approved definition.\n\n"
            "Commit slice: One slice.\n\n"
            "Verification: `pytest` passes.\n\n"
            "Invariants: Keep unrelated behavior unchanged."
        )
        milestone = (
            "## Outcome\n\nAs a user, I want the change.\n\n"
            "**Scope:** In scope: the slice.\n\n"
            "Prerequisites: The approved definition.\n\n"
            "Steps: Implement, then verify."
        )
        self.assertEqual(plan_detail.task_issues(task), [])
        self.assertEqual(plan_detail.milestone_issues(milestone), [])

    def test_touch_must_name_a_concrete_path(self) -> None:
        task = TASK.replace("src/app.py, tests/test_app.py", "the parser")
        issues = plan_detail.task_issues(task)
        self.assertEqual([issue.section for issue in issues], ["Touch"])
        self.assertIn("concrete path", issues[0].message)

    def test_document_needs_a_milestone_and_a_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "t.db"))
            empty = document()
            empty["milestones"] = []
            with self.assertRaisesRegex(plan_document.PlanDocumentError, "at least one milestone"):
                plan_document.validate_document(store, empty)
            taskless = document()
            taskless["milestones"][0]["tasks"] = []
            with self.assertRaisesRegex(plan_document.PlanDocumentError, "at least one task"):
                plan_document.validate_document(store, taskless)

    def test_validate_document_refuses_a_shallow_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "t.db"))
            with self.assertRaisesRegex(
                plan_document.PlanDocumentError,
                "milestones\\[0\\]\\.tasks\\[0\\]: resume contract incomplete: .*Guardrails",
            ):
                plan_document.validate_document(store, document(task_desc="Approach: do it."))

    def test_apply_refuses_a_stored_shallow_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "t.db"))
            stored = plan_document.load_normalized(document(task_desc="Approach: do it."))
            with self.assertRaisesRegex(plan_document.PlanDocumentError, "resume contract"):
                plan_apply.apply(store, stored)

    def test_formalize_refuses_a_shallow_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "t.db"))
            draft = draft_sketch.create_sketch(store, SKETCH)
            with self.assertRaisesRegex(plan_document.PlanDocumentError, "resume contract"):
                draft_sketch.formalize(
                    store,
                    draft.id,
                    document(milestone_desc="As a user, I want it."),
                    base_revision=1,
                )


if __name__ == "__main__":
    unittest.main()
