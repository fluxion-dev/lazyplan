"""The preview document is structured before the panel renders it."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store
from lazyplan.tui.views.preview import PreviewBlock, PreviewDocument, build_preview


class PreviewDocumentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        plan = self.store.add_plan("Plan title", "What we build", goal="Why we build")
        milestone = self.store.add_milestone(plan.id, "Milestone title", "Details")
        task = self.store.add_task(milestone.id, "Task title", "Task details")
        self.plan = plan
        self.task = task

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_document_renders_header_blocks_and_footer(self) -> None:
        document = PreviewDocument(
            header="header",
            breadcrumb="breadcrumb",
            meta=("meta",),
            blocks=(PreviewBlock("why", ("because",)),),
            footer="footer",
        )
        self.assertEqual(
            document.render(),
            "header\nbreadcrumb\nmeta\n\n[dim]why[/]\nbecause\n\nfooter",
        )

    def test_plan_preview_keeps_order_and_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        document = build_preview(self.store, "plan", self.plan.id, full, [])
        text = document.render()
        self.assertIn("P1", text)
        self.assertIn("[dim]why[/]", text)
        self.assertIn("Why we build", text)
        self.assertIn("[dim]what[/]", text)
        self.assertIn("[dim]next[/]", text)
        self.assertIn("enter open", text)

    def test_task_preview_includes_breadcrumb_and_details(self) -> None:
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        document = build_preview(self.store, "task", self.task.id, full, [])
        text = document.render()
        task = full["task"]
        self.assertIn(
            f"P{self.plan.id} › M{task['milestone_id']} › T{self.task.id}",
            text,
        )
        self.assertIn("[dim]details[/]", text)
        self.assertIn("Task details", text)


if __name__ == "__main__":
    unittest.main()
