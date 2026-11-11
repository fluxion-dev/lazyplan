"""The preview document is structured before the panel renders it."""

from __future__ import annotations

import os
import re
import tempfile
import unittest

from lazyplan.store import Store

try:
    from lazyplan.presentation.tui.views.control import build_control_strip
    from lazyplan.presentation.tui.views.preview import (
        PreviewBlock,
        PreviewDocument,
        build_preview,
    )
except ImportError:  # pragma: no cover - stdlib-only interpreter
    PreviewBlock = PreviewDocument = build_preview = build_control_strip = None  # type: ignore[assignment]

try:
    from textual.widgets import Static, Tree

    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    Static = Tree = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]


@unittest.skipUnless(build_preview is not None, "textual/rich not installed")
class PreviewDocumentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "t.db"))
        plan = self.store.add_plan("Plan title", "What we build", goal="Why we build")
        milestone = self.store.add_milestone(plan.id, "Milestone title", "Details")
        task = self.store.add_task(milestone.id, "Task title", "Task details")
        self.plan = plan
        self.milestone = milestone
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
            "header\nbreadcrumb\nmeta\n\n[bold]WHY[/]\nbecause\n\nfooter",
        )

    def test_section_headings_become_width_aware_bars(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        body = build_preview(self.store, "plan", self.plan.id, full, []).render_body(width=40)
        bars = [line for line in body.splitlines() if "[on $lp-surface-raised]" in line]
        self.assertGreaterEqual(len(bars), 4)
        for bar in bars:
            self.assertEqual(len(re.sub(r"\[[^\]]+\]", "", bar)), 40)

    def test_section_spacing_keeps_one_blank_before_each_bar(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        lines = (
            build_preview(self.store, "plan", self.plan.id, full, [])
            .render_body(width=40)
            .splitlines()
        )
        self.assertNotEqual(lines[0], "")
        self.assertNotEqual(lines[-1], "")
        self.assertFalse(
            any(
                first == "" and second == ""
                for first, second in zip(lines, lines[1:], strict=False)
            )
        )
        for index, line in enumerate(lines):
            if "[on $lp-surface-raised]" not in line:
                continue
            if index:
                self.assertEqual(lines[index - 1], "")
            self.assertNotEqual(lines[index + 1], "")

    def test_plain_render_keeps_the_bold_heading_grammar(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("[bold]MILESTONES", text)
        self.assertNotIn("[on $lp-surface-raised]", text)

    def test_plan_preview_keeps_order_and_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        document = build_preview(self.store, "plan", self.plan.id, full, [])
        text = document.render()
        self.assertIn("P1", text)
        self.assertIn("[bold]WHY[/]", text)
        self.assertIn("Why we build", text)
        self.assertIn("[bold]WHAT[/]", text)
        self.assertIn("[bold]NEXT[/]", text)
        self.assertIn("Task title", text)

    def test_plan_preview_milestones_are_title_only(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        lines = build_preview(self.store, "plan", self.plan.id, full, []).render().splitlines()
        heading = next(index for index, line in enumerate(lines) if "MILESTONES" in line)
        row = lines[heading + 1]
        self.assertIn("Milestone title", row)
        self.assertNotIn("Details", row)
        self.assertNotIn(f"M{self.milestone.id}", row)
        self.assertNotIn("tasks", row)
        self.assertNotIn("○", row)

    def test_plan_preview_shows_approval_and_drift(self) -> None:
        self.store.add_revision(self.plan.id, "a" * 64, "{}", reason="initial")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("[bold]APPROVAL[/]", text)
        self.assertIn("r1", text)
        self.assertIn("in sync", text)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("changes since approval", text)
        self.assertIn("title: rename", text)

    def test_plan_preview_shows_open_questions(self) -> None:
        self.store.add_question(self.plan.id, "Which host?")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("[bold]QUESTIONS 1 OPEN[/]", text)
        self.assertIn("Which host?", text)
        self.assertNotIn("1 open questions", text)

    def test_plan_preview_shows_references(self) -> None:
        self.store.link_ref(self.plan.id, "https://github.com/o/r/issues/7", title="Epic")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("[bold]REFERENCES 1[/]", text)
        self.assertIn("Epic", text)
        self.assertNotIn("1 references", text)

    def test_task_preview_shows_proof(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0, actor="ci")
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        text = build_preview(self.store, "task", self.task.id, full, []).render()
        self.assertIn("[bold]PROOF[/]", text)
        self.assertIn("pytest", text)
        self.assertIn("✓", text)
        self.assertIn("exit 0", text)

    def test_task_preview_includes_breadcrumb_and_details(self) -> None:
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        document = build_preview(self.store, "task", self.task.id, full, [])
        text = document.render()
        task = full["task"]
        self.assertIn(f"P{self.plan.id}", text)
        self.assertIn(f"M{task['milestone_id']}", text)
        self.assertIn(f"T{self.task.id}", text)
        self.assertIn(f"▹ T{self.task.id}", text)
        self.assertIn("[bold]DETAILS[/]", text)
        self.assertIn("Task details", text)

    def test_plan_control_strip_names_attention(self) -> None:
        self.store.add_revision(self.plan.id, "a" * 64, "{}", reason="initial")
        self.store.add_question(self.plan.id, "Which host?")
        self.store.claim_task(self.task.id, "alice", 300)
        self.store.set_blocked(self.task.id, True, "waiting", actor="t")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        strip = build_control_strip(self.store, "plan", self.plan.id, full)
        self.assertIn("[bold]attention[/]", strip)
        self.assertIn("question", strip)
        self.assertIn("blocked", strip)

    def test_task_control_strip_reports_overlap_and_open_criteria(self) -> None:
        other = self.store.add_task(self.milestone.id, "Other", "Other details")
        self.store.add_criteria("task", self.task.id, "Works")
        self.store.add_touchpoint(self.task.id, "src/app", actor="t")
        self.store.add_touchpoint(other.id, "src/app/api.py", actor="t")
        self.store.claim_task(self.task.id, "alice", 300)
        self.store.claim_task(other.id, "bob", 300)
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        strip = build_control_strip(self.store, "task", self.task.id, full)
        self.assertIn("[bold]attention[/]", strip)
        self.assertIn("claim @alice", strip)
        self.assertIn("criterion", strip)
        self.assertIn("overlap", strip)

    def test_control_strip_says_when_attention_is_clear(self) -> None:
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        strip = build_control_strip(self.store, "task", self.task.id, full)
        self.assertIn("✓ clear", strip)


@unittest.skipUnless(create_app is not None, "textual not installed")
class PreviewResizeTest(unittest.IsolatedAsyncioTestCase):
    async def test_section_bars_follow_the_preview_width_on_resize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "resize.db"))
            plan = store.add_plan("Plan title", "What we build", goal="Why we build")
            milestone = store.add_milestone(plan.id, "Milestone title", "Details")
            store.add_task(milestone.id, "Task title", "Task details")
            app = create_app(str(store.path))
            async with app.run_test(size=(110, 35)) as pilot:
                await pilot.pause()
                tree = app.query_one("#tree", Tree)
                tree.focus()
                tree.select_node(tree.root.children[0])
                await pilot.pause()
                body = app.query_one("#preview-body", Static)
                first_width = body.size.width
                bar = next(
                    line
                    for line in str(body.render()).splitlines()
                    if line.strip().startswith("WHY")
                )
                self.assertEqual(len(bar), first_width)
                await pilot.resize_terminal(150, 35)
                await pilot.pause()
                body = app.query_one("#preview-body", Static)
                wider = body.size.width
                self.assertGreater(wider, first_width)
                bar = next(
                    line
                    for line in str(body.render()).splitlines()
                    if line.strip().startswith("WHY")
                )
                self.assertEqual(len(bar), wider)


if __name__ == "__main__":
    unittest.main()
