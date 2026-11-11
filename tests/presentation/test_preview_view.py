"""The preview document is structured Markdown before the panel renders it."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store

try:
    from textual.widgets import Markdown, Static, Tree

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.views.control import build_control_strip
    from lazyplan.presentation.tui.views.preview import (
        PreviewBlock,
        PreviewDocument,
        build_preview,
    )
    from lazyplan.presentation.tui.widgets.preview_panel import PreviewPanel
except ImportError:  # pragma: no cover - stdlib-only interpreter
    PreviewBlock = PreviewDocument = build_preview = build_control_strip = None  # type: ignore[assignment]
    create_app = Markdown = PreviewPanel = Static = Tree = None  # type: ignore[assignment,misc]


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
            "header\nbreadcrumb\nmeta\n\n## WHY\nbecause\n\nfooter",
        )

    def test_section_headings_become_markdown_h2(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        body = build_preview(self.store, "plan", self.plan.id, full, []).render_markdown()
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        self.assertGreaterEqual(len(headings), 4)
        for heading in headings:
            self.assertEqual(heading, heading.upper())

    def test_section_spacing_keeps_one_blank_between_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        lines = (
            build_preview(self.store, "plan", self.plan.id, full, []).render_markdown().splitlines()
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
            if not line.startswith("## "):
                continue
            if index:
                self.assertEqual(lines[index - 1], "")
            self.assertNotEqual(lines[index + 1], "")

    def test_plain_render_keeps_the_markdown_heading_grammar(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("## MILESTONES 1", text)
        self.assertNotIn("[on $lp-surface-raised]", text)

    def test_structured_titles_are_markdown_escaped(self) -> None:
        plan = self.store.add_plan("Plan", "What we build", goal="raw **prose**")
        milestone = self.store.add_milestone(plan.id, "Milestone *bold* [x]", "Details")
        task = self.store.add_task(milestone.id, "Task #hash", "Task details")
        full = self.store.get_full("plan", plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", plan.id, full, []).render()
        self.assertIn("Milestone \\*bold\\* \\[x\\]", text)
        self.assertIn(f"**T{task.id}** Task \\#hash", text)
        self.assertIn("raw **prose**", text)

    def test_plan_preview_keeps_order_and_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        document = build_preview(self.store, "plan", self.plan.id, full, [])
        text = document.render()
        self.assertIn("P1", text)
        self.assertIn("## WHY", text)
        self.assertIn("Why we build", text)
        self.assertIn("## WHAT", text)
        self.assertIn("## NEXT", text)
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
        self.assertIn("## APPROVAL", text)
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
        self.assertIn("## QUESTIONS 1 OPEN", text)
        self.assertIn("Which host?", text)
        self.assertNotIn("1 open questions", text)

    def test_plan_preview_shows_references(self) -> None:
        self.store.link_ref(self.plan.id, "https://github.com/o/r/issues/7", title="Epic")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview(self.store, "plan", self.plan.id, full, []).render()
        self.assertIn("## REFERENCES 1", text)
        self.assertIn("[Epic](<https://github.com/o/r/issues/7>)", text)

    def test_task_preview_shows_proof(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0, actor="ci")
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        text = build_preview(self.store, "task", self.task.id, full, []).render()
        self.assertIn("## PROOF", text)
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
        self.assertIn("## DETAILS", text)
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
class PreviewMarkdownTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_body_is_markdown_and_tracks_the_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "markdown.db"))
            first = store.add_plan("First plan", "First what", goal="First why")
            store.add_plan("Second plan", "Second what", goal="Second why")
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                tree = app.query_one("#tree", Tree)
                tree.focus()
                node = next(
                    child for child in tree.root.children if child.data.get("id") == first.id
                )
                tree.select_node(node)
                await pilot.pause()
                body = app.query_one("#preview-body", Markdown)
                self.assertIsInstance(app.query_one("#preview-head"), Static)
                self.assertIsInstance(app.query_one("#preview-strip"), Static)
                self.assertIn("## WHY", body.source or "")
                self.assertIn("First why", body.source or "")
                tree.select_node(next(child for child in tree.root.children if child is not node))
                await pilot.pause()
                body = app.query_one("#preview-body", Markdown)
                self.assertIn("Second why", body.source or "")
                self.assertNotIn("First why", body.source or "")

    async def test_links_open_only_http_and_https(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(os.path.join(tmp, "links.db"))
            store.add_plan("Plan", "What", goal="Why")
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = app.query_one("#preview", PreviewPanel)
                body = app.query_one("#preview-body", Markdown)
                for href in ("https://example.com/doc", "http://example.com/doc"):
                    with (
                        mock.patch.object(app, "open_url") as opener,
                        mock.patch.object(app, "notify") as notify,
                    ):
                        panel._open_link(Markdown.LinkClicked(body, href))
                        opener.assert_called_once_with(href)
                        notify.assert_called_once()
                for href in ("file:///etc/passwd", "javascript:alert(1)"):
                    with (
                        mock.patch.object(app, "open_url") as opener,
                        mock.patch.object(app, "notify") as notify,
                    ):
                        panel._open_link(Markdown.LinkClicked(body, href))
                        opener.assert_not_called()
                        notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
