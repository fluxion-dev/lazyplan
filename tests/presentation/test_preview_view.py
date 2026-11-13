"""The preview document is structured Markdown before the panel renders it."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.core.entities import Status
from lazyplan.store import Store

try:
    from textual.widgets import Markdown, Static, Tree
    from textual.widgets._markdown import MarkdownH2

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.views.control import build_control_strip
    from lazyplan.presentation.tui.views.preview import (
        PreviewBlock,
        PreviewDocument,
        acceptance_block,
        build_preview,
    )
    from lazyplan.presentation.tui.widgets.preview_panel import PreviewPanel
except ImportError:  # pragma: no cover - stdlib-only interpreter
    PreviewBlock = PreviewDocument = acceptance_block = None  # type: ignore[assignment]
    build_preview = build_control_strip = None  # type: ignore[assignment]
    create_app = Markdown = PreviewPanel = Static = Tree = None  # type: ignore[assignment,misc]
    MarkdownH2 = None  # type: ignore[assignment,misc]


GFM_FIXTURE = """**bold** text

- one
- two

> quoted

```python
print("hi")
```

| a | b |
|---|---|
| 1 | 2 |

[site](https://example.com)
"""


@unittest.skipUnless(build_preview is not None, "textual/rich not installed")
class PreviewDocumentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
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
            meta_line="meta line",
            blocks=(PreviewBlock("why", ("because",)),),
            footer="footer",
        )
        self.assertEqual(
            document.render(),
            "header\nmeta line\n## WHY\nbecause\n\nfooter",
        )

    def test_section_headings_become_markdown_h2(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        body = build_preview("plan", self.plan.id, full).render_markdown()
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        self.assertGreaterEqual(len(headings), 2)
        for heading in headings:
            self.assertEqual(heading, heading.upper())

    def test_section_spacing_keeps_one_blank_between_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        lines = build_preview("plan", self.plan.id, full).render_markdown().splitlines()
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
        text = build_preview("plan", self.plan.id, full).render()
        self.assertIn("## MILESTONES 1", text)
        self.assertNotIn("[on $lp-surface-raised]", text)

    def test_structured_titles_are_markdown_escaped(self) -> None:
        plan = self.store.add_plan("Plan", "What we build", goal="raw **prose**")
        milestone = self.store.add_milestone(plan.id, "Milestone *bold* [x]", "Details")
        task = self.store.add_task(milestone.id, "Task #hash", "Task details")
        full = self.store.get_full("plan", plan.id)
        assert full is not None
        text = build_preview("plan", plan.id, full).render()
        self.assertIn(f"M{milestone.id}  Milestone \\*bold\\* \\[x\\]", text)
        self.assertIn("raw **prose**", text)
        milestone_full = self.store.get_full("milestone", milestone.id)
        assert milestone_full is not None
        milestone_text = build_preview("milestone", milestone.id, milestone_full).render()
        self.assertIn(f"T{task.id}  Task \\#hash", milestone_text)

    def test_plan_preview_keeps_order_and_sections(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        document = build_preview("plan", self.plan.id, full)
        text = document.render()
        self.assertIn("P1", text)
        self.assertIn("## WHY", text)
        self.assertIn("Why we build", text)
        self.assertNotIn("## WHAT", text)
        self.assertNotIn("What we build", text)
        self.assertIn("## MILESTONES 1", text)
        self.assertIn("Milestone title", text)
        self.assertNotIn("## NEXT", text)
        self.assertNotIn("Task title", text)

    def test_plan_headline_keeps_only_the_first_paragraph(self) -> None:
        plan = self.store.add_plan(
            "Long plan",
            "What we build",
            goal="First sentence stays.\n\nSecond paragraph is detail.",
        )
        full = self.store.get_full("plan", plan.id)
        assert full is not None
        text = build_preview("plan", plan.id, full).render_markdown()
        why = text.split("## WHY", 1)[1].split("## ", 1)[0]
        self.assertIn("First sentence stays.", why)
        self.assertNotIn("Second paragraph", why)

    def test_long_headlines_clamp_at_a_word_boundary(self) -> None:
        plan = self.store.add_plan("Long plan", "What", goal="word " * 60)
        full = self.store.get_full("plan", plan.id)
        assert full is not None
        text = build_preview("plan", plan.id, full).render_markdown()
        why = text.split("## WHY", 1)[1].split("## ", 1)[0].strip()
        self.assertTrue(why.endswith("…"))
        self.assertLessEqual(len(why), 121)
        self.assertNotIn("  ", why)

    def test_milestone_details_are_one_headline(self) -> None:
        milestone = self.store.add_milestone(
            self.plan.id,
            "Slice",
            "First line of intent.\n\nINVEST: detail stays behind.",
        )
        full = self.store.get_full("milestone", milestone.id)
        assert full is not None
        text = build_preview("milestone", milestone.id, full).render_markdown()
        details = text.split("## DETAILS", 1)[1].split("## ", 1)[0]
        self.assertIn("First line of intent.", details)
        self.assertNotIn("INVEST", details)

    def test_plan_preview_shows_the_registered_worktree(self) -> None:
        self.store.register_plan_worktree(
            self.plan.id,
            "/repos/lazyplan",
            "/repos/lazyplan--plan-1-plan-title",
            branch="plan/1-plan-title",
        )
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None

        text = build_preview("plan", self.plan.id, full).render()

        self.assertIn("## WORKTREES", text)
        self.assertIn("isolation required", text)
        self.assertIn("plan/1-plan-title", text)
        self.assertIn("lazyplan--plan-1-plan-title", text)

    def test_grandfathered_plan_preview_omits_worktrees(self) -> None:
        plan = self.store.add_plan("Old plan", worktree_required=False)
        full = self.store.get_full("plan", plan.id)
        assert full is not None

        text = build_preview("plan", plan.id, full).render()

        self.assertNotIn("## WORKTREES", text)

    def test_plan_preview_milestones_are_header_rows(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        lines = build_preview("plan", self.plan.id, full).render().splitlines()
        heading = next(index for index, line in enumerate(lines) if "MILESTONES" in line)
        row = lines[heading + 1]
        self.assertEqual(row, f"- M{self.milestone.id}  Milestone title · 0/1")
        self.assertNotIn("Details", row)
        self.assertNotIn("tasks", row)

    def test_acceptance_block_lists_open_criteria_only(self) -> None:
        criteria = [
            {"id": 1, "text": "done one", "done": True, "evidence": {"state": "pass", "count": 2}},
            {"id": 2, "text": "open one", "done": False, "evidence": {}},
            {"id": 3, "text": "open two", "done": False, "evidence": {"state": "fail", "count": 1}},
            {"id": 4, "text": "done two", "done": True, "evidence": {}},
        ]
        block = acceptance_block(criteria, detailed=True)
        assert block is not None
        self.assertEqual(block.heading, "acceptance 2/4 · 2 open")
        self.assertEqual(
            block.lines,
            (
                "- open one",
                "- open two",
            ),
        )

    def test_acceptance_block_is_absent_when_every_criterion_is_done(self) -> None:
        criteria = [{"id": 1, "text": "done", "done": True, "evidence": {}}]
        self.assertIsNone(acceptance_block(criteria, detailed=True))
        self.assertIsNone(acceptance_block(criteria))

    def test_plan_preview_lists_open_criteria_only(self) -> None:
        criteria = [
            self.store.add_criteria("plan", self.plan.id, f"criterion {index}")
            for index in range(7)
        ]
        self.store.update_criterion(criteria[0].id, done=True)
        self.store.update_criterion(criteria[1].id, done=True)
        self.store.add_evidence(criteria[0].id, command="pytest", exit_code=0, actor="ci")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render_markdown()
        acceptance = text.split("## ACCEPTANCE", 1)[1].split("## ", 1)[0]
        for criterion in criteria[2:5]:
            self.assertIn(criterion.text, acceptance)
        self.assertNotIn(criteria[5].text, acceptance)
        self.assertNotIn(criteria[6].text, acceptance)
        self.assertNotIn(f"C{criteria[0].id}", acceptance)
        self.assertNotIn(f"C{criteria[1].id}", acceptance)
        self.assertIn("2/7 · 5 OPEN", acceptance)
        self.assertIn("- 2 more open", acceptance)

    def test_acceptance_list_caps_at_three_rows(self) -> None:
        criteria = [
            {"id": index, "text": f"open {index}", "done": False, "evidence": {}}
            for index in range(4)
        ]
        block = acceptance_block(criteria, detailed=True)
        assert block is not None
        self.assertEqual(len(block.lines), 4)
        self.assertEqual(block.lines[-1], "- 1 more open")

    def test_plan_preview_without_criteria_has_no_acceptance_block(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render_markdown()
        self.assertNotIn("## ACCEPTANCE", text)

    def test_unapproved_plan_has_no_approval_block(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render_markdown()
        self.assertNotIn("## APPROVAL", text)
        self.assertNotIn("no approved revision", text)

    def test_notes_and_source_never_render(self) -> None:
        self.store.add_note("plan", self.plan.id, "a private note", actor="t")
        self.store.add_note("task", self.task.id, "a task note", actor="t")
        self.store.link_commit("task", self.task.id, "a" * 40, "subject", actor="t")
        for kind, obj_id in (
            ("plan", self.plan.id),
            ("milestone", self.milestone.id),
            ("task", self.task.id),
        ):
            full = self.store.get_full(kind, obj_id)
            assert full is not None
            text = build_preview(kind, obj_id, full).render_markdown()
            self.assertNotIn("## NOTES", text)
            self.assertNotIn("## SOURCE", text)
            self.assertNotIn("a private note", text)
            self.assertNotIn("a task note", text)

    def test_milestone_preview_keeps_the_short_acceptance_list(self) -> None:
        criteria = [
            self.store.add_criteria("milestone", self.milestone.id, f"milestone criterion {index}")
            for index in range(4)
        ]
        full = self.store.get_full("milestone", self.milestone.id)
        assert full is not None
        text = build_preview("milestone", self.milestone.id, full).render_markdown()
        acceptance = text.split("## ACCEPTANCE", 1)[1].split("## ", 1)[0]
        self.assertNotIn(f"C{criteria[0].id}", acceptance)
        self.assertEqual(acceptance.count("- milestone criterion"), 3)

    def test_child_rows_use_words_not_glyphs(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render_markdown()
        for icon in ("○", "◐", "●", "◈", "◇", "▹", "✓", "✗", "—", "▰", "▱"):
            self.assertNotIn(icon, text)

    def test_task_rows_carry_one_state_word(self) -> None:
        self.store.set_status_raw("task", self.task.id, Status.DOING)
        full = self.store.get_full("milestone", self.milestone.id)
        assert full is not None
        text = build_preview("milestone", self.milestone.id, full).render_markdown()
        self.assertIn(f"- T{self.task.id}  Task title · doing", text)

        self.store.set_blocked(self.task.id, True, "waiting", actor="t")
        full = self.store.get_full("milestone", self.milestone.id)
        assert full is not None
        text = build_preview("milestone", self.milestone.id, full).render_markdown()
        self.assertIn(f"- T{self.task.id}  Task title · blocked", text)

    def test_acceptance_rows_keep_plain_prose(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "Run `pytest` in the repo")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0, actor="ci")
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        text = build_preview("task", self.task.id, full).render_markdown()
        self.assertIn("- Run `pytest` in the repo · proven · pytest · exit 0", text)
        self.assertNotIn("\\`", text)
        self.assertNotIn(f"C{criterion.id}", text)

    def test_milestone_preview_tasks_are_header_rows(self) -> None:
        second = self.store.add_task(
            self.milestone.id, "Second task", "Second details\nmore detail"
        )
        full = self.store.get_full("milestone", self.milestone.id)
        assert full is not None
        lines = build_preview("milestone", self.milestone.id, full).render().splitlines()
        heading = next(index for index, line in enumerate(lines) if line.startswith("## TASKS"))
        rows = [line for line in lines[heading + 1 :] if line.startswith("- ")]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], f"- T{self.task.id}  Task title")
        self.assertEqual(rows[1], f"- T{second.id}  Second task")
        text = "\n".join(rows)
        self.assertNotIn("Task details", text)
        self.assertNotIn("Second details", text)
        self.assertNotIn("more detail", text)

    def test_plan_preview_shows_approval_and_drift(self) -> None:
        self.store.add_revision(self.plan.id, "a" * 64, "{}", reason="initial")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render()
        self.assertIn("## APPROVAL", text)
        self.assertIn("r1", text)
        self.assertIn("in sync", text)
        self.store.update_task(self.task.id, title="Renamed", reason="rename")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render()
        self.assertIn("changes since approval", text)
        self.assertIn("title: rename", text)

    def test_plan_preview_shows_open_questions(self) -> None:
        self.store.add_question(self.plan.id, "Which host?")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render()
        self.assertIn("## QUESTIONS 1 OPEN", text)
        self.assertIn("Which host?", text)
        self.assertNotIn("1 open questions", text)

    def test_plan_preview_shows_references(self) -> None:
        self.store.link_ref(self.plan.id, "https://github.com/o/r/issues/7", title="Epic")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        text = build_preview("plan", self.plan.id, full).render()
        self.assertIn("## REFERENCES 1", text)
        self.assertIn("[Epic](<https://github.com/o/r/issues/7>)", text)

    def test_task_preview_shows_proof(self) -> None:
        criterion = self.store.add_criteria("task", self.task.id, "Works")
        self.store.add_evidence(criterion.id, command="pytest", exit_code=0, actor="ci")
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        text = build_preview("task", self.task.id, full).render()
        self.assertIn("## PROOF", text)
        self.assertIn("pytest", text)
        self.assertIn("proven", text)
        self.assertIn("exit 0", text)
        self.assertNotIn("✓", text)

    def test_task_preview_shows_context_line_and_details(self) -> None:
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        document = build_preview("task", self.task.id, full)
        text = document.render()
        task = full["task"]
        head = document.render_head().splitlines()
        self.assertEqual(head[0], "[bold]Task title[/]")
        self.assertEqual(len(head), 2)
        self.assertIn(f"M{task['milestone_id']}", text)
        self.assertIn(f"T{self.task.id}", text)
        self.assertEqual(head[1], f"[dim]T{self.task.id} · M{task['milestone_id']} · todo[/]")
        self.assertNotIn("▹", text)
        self.assertNotIn("◈", text)
        self.assertIn("## DETAILS", text)
        self.assertIn("Task details", text)

    def test_plan_head_is_the_title_and_one_meta_line(self) -> None:
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        document = build_preview("plan", self.plan.id, full)
        head = document.render_head().splitlines()
        self.assertEqual(head[0], "[bold]Plan title[/]")
        self.assertEqual(len(head), 2)
        self.assertIn(f"P{self.plan.id}", head[1])
        self.assertIn("0/1 tasks", head[1])
        for icon in ("◈", "◇", "▹", "○", "◐", "●"):
            self.assertNotIn(icon, document.render_head())

    def test_plan_control_strip_names_attention(self) -> None:
        self.store.add_revision(self.plan.id, "a" * 64, "{}", reason="initial")
        self.store.add_question(self.plan.id, "Which host?")
        self.store.claim_task(self.task.id, "alice", 300)
        self.store.set_blocked(self.task.id, True, "waiting", actor="t")
        full = self.store.get_full("plan", self.plan.id)
        assert full is not None
        strip = build_control_strip(self.store, "plan", self.plan.id, full)
        self.assertNotIn("[bold]", strip)
        self.assertNotIn("✓", strip)
        self.assertIn("1 open question", strip)
        self.assertIn("1 blocked task", strip)

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
        self.assertNotIn("[bold]", strip)
        self.assertNotIn("@alice", strip)
        self.assertIn("1 open criterion", strip)
        self.assertIn("1 overlap", strip)

    def test_control_strip_is_empty_when_attention_is_clear(self) -> None:
        full = self.store.get_full("task", self.task.id)
        assert full is not None
        strip = build_control_strip(self.store, "task", self.task.id, full)
        self.assertEqual(strip, "")


@unittest.skipUnless(create_app is not None, "textual not installed")
class PreviewMarkdownTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_body_is_markdown_and_tracks_the_selection(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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

    async def test_overview_widget_renders_open_plan_criteria(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = Store(os.path.join(tmp, "criteria.db"))
            plan = store.add_plan("Plan", "What", goal="Why")
            criteria = [
                store.add_criteria("plan", plan.id, f"widget criterion {index}")
                for index in range(4)
            ]
            store.update_criterion(criteria[0].id, done=True)
            store.add_evidence(criteria[0].id, command="pytest", exit_code=0, actor="ci")
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                tree = app.query_one("#tree", Tree)
                tree.focus()
                tree.select_node(tree.root.children[0])
                await pilot.pause()
                source = app.query_one("#preview-body", Markdown).source or ""
                for criterion in criteria[1:]:
                    self.assertIn(criterion.text, source)
                self.assertNotIn(f"C{criteria[0].id}", source)
                self.assertLess(
                    source.index("widget criterion 1"), source.index("widget criterion 2")
                )

    async def test_gfm_prose_renders_as_markdown_blocks(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = Store(os.path.join(tmp, "gfm.db"))
            plan = store.add_plan("Plan", "What", goal="Why")
            milestone = store.add_milestone(plan.id, "Slice", "Details")
            task = store.add_task(milestone.id, "Task", GFM_FIXTURE)
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app._expanded.update({("plan", plan.id), ("milestone", milestone.id)})
                app.refresh_all()
                await pilot.pause()
                app.select_row("task", task.id)
                await pilot.pause()
                body = app.query_one("#preview-body", Markdown)
                self.assertIn("**bold** text", body.source or "")
                blocks = [type(child).__name__ for child in body.children]
                for expected in (
                    "MarkdownBulletList",
                    "MarkdownBlockQuote",
                    "MarkdownFence",
                    "MarkdownTable",
                ):
                    self.assertIn(expected, blocks)
                paragraphs = [
                    child for child in body.children if type(child).__name__ == "MarkdownParagraph"
                ]
                styles = [str(span.style) for child in paragraphs for span in child._content.spans]
                self.assertTrue(any("strong" in style for style in styles))
                self.assertTrue(any("link(" in style for style in styles))

    async def test_section_bars_fill_the_body_and_use_the_raised_surface(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = Store(os.path.join(tmp, "bars.db"))
            store.add_plan("Plan", "What", goal="Why")
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                tree = app.query_one("#tree", Tree)
                tree.focus()
                tree.select_node(tree.root.children[0])
                await pilot.pause()
                body = app.query_one("#preview-body", Markdown)
                bars = list(body.query(MarkdownH2))
                self.assertGreaterEqual(len(bars), 2)
                expected = app.theme_variables["lp-surface-raised"]
                for bar in bars:
                    self.assertEqual(bar.region.width, body.size.width)
                    self.assertEqual(bar.styles.background.hex, expected)

    async def test_section_bars_keep_one_line_above_and_below(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = Store(os.path.join(tmp, "spacing.db"))
            store.add_plan("Plan", "What", goal="Why\n\n## Inner heading\n\nProse")
            app = create_app(str(store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                tree = app.query_one("#tree", Tree)
                tree.focus()
                tree.select_node(tree.root.children[0])
                await pilot.pause()
                body = app.query_one("#preview-body", Markdown)
                blocks = list(body.children)
                bars = [
                    index for index, block in enumerate(blocks) if isinstance(block, MarkdownH2)
                ]
                self.assertGreaterEqual(len(bars), 2)
                for index in bars:
                    bar = blocks[index]
                    margin = bar.styles.margin
                    self.assertEqual((margin.top, margin.bottom), (1, 1))
                    if index:
                        self.assertEqual(bar.region.y - blocks[index - 1].region.bottom, 1)
                    if index + 1 < len(blocks):
                        self.assertEqual(blocks[index + 1].region.y - bar.region.bottom, 1)

    async def test_links_open_only_http_and_https(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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
