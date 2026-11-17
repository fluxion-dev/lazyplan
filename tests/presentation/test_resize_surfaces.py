"""Every TUI surface reflows at 40, 80, 120, and 160 columns.

One mounted surface walks the matrix; each case reads regions, virtual
content width, selection, cursor, and scroll. Cases marked ``expectedFailure``
record a defect from ``resize-audit.md`` until its fix task lands.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from lazyplan import services
from lazyplan.core.entities import PlanRevision, Status
from lazyplan.core.policies.revisions import Change
from lazyplan.presentation import setup
from lazyplan.services.revisions import DiffEntry, DiffResult
from lazyplan.store import Store

try:
    from rich.cells import cell_len
    from textual.widgets import Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import (
        HealthScreen,
        HelpScreen,
        PaletteScreen,
        SetupWizardScreen,
        TextScreen,
        UpdateScreen,
    )
    from lazyplan.presentation.tui.screens.export import ExportScreen
    from lazyplan.presentation.tui.screens.forms import (
        ConfirmScreen,
        CriterionScreen,
        FilterPromptScreen,
        NewPlanScreen,
    )
    from lazyplan.presentation.tui.screens.hub_coordination import (
        ClaimsHub,
        CommentsHub,
    )
    from lazyplan.presentation.tui.screens.hub_kinds import (
        CriteriaHub,
        EvidenceHub,
        QuestionsHub,
        ReferencesHub,
    )
    from lazyplan.presentation.tui.screens.hub_provenance import (
        ActivityHub,
        PullRequestHub,
    )
    from lazyplan.presentation.tui.screens.maintenance import MaintenanceScreen
    from lazyplan.presentation.tui.screens.plan_diff import PlanDiffScreen
    from lazyplan.presentation.tui.screens.source import SourceScreen
except ImportError:  # pragma: no cover - textual not installed
    cell_len = None  # type: ignore[assignment]
    Static = None  # type: ignore[assignment,misc]
    create_app = None  # type: ignore[assignment]
    HealthScreen = HelpScreen = PaletteScreen = None  # type: ignore[assignment]
    SetupWizardScreen = TextScreen = UpdateScreen = None  # type: ignore[assignment]
    ExportScreen = None  # type: ignore[assignment]
    ConfirmScreen = CriterionScreen = FilterPromptScreen = NewPlanScreen = None  # type: ignore[assignment]
    ClaimsHub = CommentsHub = None  # type: ignore[assignment]
    CriteriaHub = EvidenceHub = QuestionsHub = ReferencesHub = None  # type: ignore[assignment]
    ActivityHub = PullRequestHub = MaintenanceScreen = None  # type: ignore[assignment]
    PlanDiffScreen = SourceScreen = None  # type: ignore[assignment]

from tests.support.home import sandbox_home
from tests.support.resize import SIZES, ResizeMatrix

SHELL_PARTS = {
    "plans-active": "#plans-active",
    "agents": "#agents",
    "plans-finished": "#plans-finished",
    "git": "#git",
    "preview": "#preview",
    "metrics": "#metrics",
    "hints": "#hints",
}
SHELL_SIBLINGS = ("plans-active", "agents", "plans-finished", "git", "preview", "metrics")
HUB_PARTS = {
    "page": "#hub-page",
    "list": "#hub-list-wrap",
    "preview": "#hub-preview",
    "hints": "#hub-hints",
}
SOURCE_PARTS = {
    "page": "#source-page",
    "head": "#source-head",
    "tree": "#source-tree-wrap",
    "preview": "#source-preview",
    "hints": "#source-hints",
}
DIFF_PARTS = {
    "page": "#plan-diff-page",
    "head": "#plan-diff-head",
    "scroll": "#plan-diff-scroll",
    "body": "#plan-diff-body",
    "hints": "#plan-diff-hints",
}


def _revision() -> PlanRevision:
    return PlanRevision(
        id=1, plan_id=1, revision=2, approved_at=0.0, digest="b" * 64, snapshot="{}"
    )


DIFF = DiffResult(
    plan_id=1,
    from_revision=_revision(),
    to_revision=None,
    entries=(
        DiffEntry(
            change=Change(
                kind="task",
                action="change",
                obj_id=7,
                identity="task:7",
                title="A task title long enough to need a deliberate wrap at forty columns",
                before="old scope " * 8,
                after="new scope " * 8,
            ),
            reason="scope clarified " * 5,
        ),
    ),
    summary={"add": 0, "remove": 0, "change": 1, "move": 0, "total": 1},
)

MODALS = (
    ("new plan", NewPlanScreen, "#dlg"),
    ("confirm", lambda: ConfirmScreen("Delete plan P1 and everything below it?"), "#dlg"),
    ("filter prompt", FilterPromptScreen, "#dlg"),
    ("criterion", lambda: CriterionScreen("A criterion", creating=True), "#dlg"),
    ("help", HelpScreen, "#help"),
    ("palette", PaletteScreen, "#dlg"),
    (
        "update",
        lambda: UpdateScreen(
            "1.0", "2.0", type("Info", (), {"method": "pip", "upgradeable": True})()
        ),
        "#dlg",
    ),
    ("health", lambda: HealthScreen((), review=True), "#dlg"),
    ("notes", lambda: TextScreen("NOTES", "line one\n" + "long line " * 20), "#help"),
)
FORM_MODALS = (
    ("new plan", NewPlanScreen),
    ("confirm", lambda: ConfirmScreen("Delete plan P1 and everything below it?")),
    ("filter prompt", FilterPromptScreen),
    ("criterion", lambda: CriterionScreen("A criterion", creating=True)),
    ("help", HelpScreen),
    ("palette", PaletteScreen),
    ("notes", lambda: TextScreen("NOTES", "line one\n" + "long line " * 20)),
)


@unittest.skipUnless(create_app is not None, "textual not installed")
class _SurfaceCase(unittest.IsolatedAsyncioTestCase):
    """Shared fixture: one plan with a live claim, criteria, and a checkout."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(os.path.join(self.tmp.name, "resize.db"))
        self.plan = self.store.add_plan(
            "A long plan title that must wrap inside narrow panels",
            "What gets built across several panels.",
            goal="Every panel reflows on resize without clipping or stale widths.",
        )
        self.milestone = self.store.add_milestone(self.plan.id, "Measure every surface", "Sizes.")
        self.task = self.store.add_task(self.milestone.id, "Walk the resize matrix", "Details.")
        self.store.set_status_raw("task", self.task.id, Status.DOING)
        self.store.claim_task(self.task.id, "audit-lane")
        self.criterion = self.store.add_criteria(
            "plan", self.plan.id, "Every panel reflows on resize", actor="fixture"
        )
        self.store.add_evidence(
            self.criterion.id, command="pytest -q", exit_code=0, note="all green", actor="fixture"
        )
        self.store.add_question(
            self.plan.id, "Does the preview wrap at 40 columns?", actor="fixture"
        )
        services.link_ref(self.store, self.plan.id, "https://example.test/issue/1", actor="fixture")
        self.store.add_comment(
            "plan", self.plan.id, "A comment long enough to wrap in the preview.", actor="fixture"
        )
        checkout = self.root / "checkout"
        checkout.mkdir()
        self.store.add_repo_link(
            "plan", self.plan.id, str(checkout), "git@example.test:org/api.git"
        )
        self.store.link_commit(
            "plan",
            self.plan.id,
            "a" * 40,
            subject="Wrap the diff at every width",
            author="Fixture",
            repo_root=str(checkout),
            files=("app/a.py",),
        )

    def hubs(self) -> list[tuple[str, Any]]:
        """Every hub, with one row loaded where the fixture supports it."""
        return [
            ("criteria", CriteriaHub(self.store, "plan", self.plan.id)),
            ("evidence", EvidenceHub(self.store, self.criterion.id)),
            ("questions", QuestionsHub(self.store, self.plan.id)),
            ("references", ReferencesHub(self.store, self.plan.id)),
            ("claims", ClaimsHub(self.store)),
            ("comments", CommentsHub(self.store, "plan", self.plan.id)),
            ("pull requests", PullRequestHub(self.store, "plan", self.plan.id)),
            ("activity", ActivityHub(self.store)),
            ("maintenance", MaintenanceScreen(self.store)),
        ]


class ShellResizeTest(_SurfaceCase):
    async def test_the_shell_reflows_at_every_size(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            app.select_row("plan", self.plan.id)
            app.state.timeline_visible = True
            app._apply_layout()
            app.metrics_controller.refresh()
            await pilot.pause()
            selected = app.selected
            matrix = await ResizeMatrix("shell").walk(
                pilot,
                parts=SHELL_PARTS,
                selection=lambda: app.selected,
                scrolls=("#preview-scroll", "#git"),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                with self.subTest(size=snapshot.size):
                    snapshot.assert_inside(self)
                    snapshot.assert_no_overlap(self, SHELL_SIBLINGS)
                    self.assertEqual(snapshot.selection, selected)
                    scroll, maximum = snapshot.scroll["#preview-scroll"]
                    self.assertGreaterEqual(scroll, 0)
                    self.assertLessEqual(scroll, maximum)
                    git_scroll, git_max = snapshot.scroll["#git"]
                    self.assertLessEqual(git_scroll, git_max)
            self.assertEqual(matrix.at((120, 40)).part("metrics").region[2], 120)
            self.assertEqual(matrix.at((160, 50)).part("metrics").region[2], 160)
            self.assertIsNone(matrix.at((40, 24)).part("preview").region)
            self.assertEqual(app.selected, selected)

    async def test_the_preview_rewraps_markdown_and_keeps_its_selection(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.select_row("plan", self.plan.id)
            await pilot.pause()
            selected = app.selected
            matrix = await ResizeMatrix("preview").walk(
                pilot,
                parts={"preview": "#preview", "body": "#preview-body"},
                selection=lambda: app.selected,
                scrolls=("#preview-scroll",),
            )
            for snapshot in matrix.snapshots:
                with self.subTest(size=snapshot.size):
                    snapshot.assert_inside(self)
                    snapshot.assert_unclipped(self, ("body",))
                    self.assertEqual(snapshot.selection, selected)
                    scroll, maximum = snapshot.scroll["#preview-scroll"]
                    self.assertLessEqual(scroll, maximum)

    async def test_the_agents_card_rewraps_its_claim_rows(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause(0.3)
            body = app.query_one("#agents-body", Static)
            for size in SIZES:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                await pilot.pause()
                widest = max(
                    (cell_len(line) for line in str(body.render()).splitlines()), default=0
                )
                self.assertLessEqual(widest, body.content_size.width, f"agents at {size}")

    async def test_the_timeline_redraws_for_the_new_width(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.select_row("plan", self.plan.id)
            app.state.timeline_visible = True
            app._apply_layout()
            app.metrics_controller.refresh()
            await pilot.pause()
            card = app.query_one("#metric-timeline")
            plot = app.query_one("#metric-timeline-plot")
            for size in SIZES:
                await pilot.resize_terminal(*size)
                await pilot.pause()
                await pilot.pause()
                if not app.query_one("#metrics").display:
                    continue
                self.assertEqual(card.drawn_width, plot.size.width - 2, f"timeline at {size}")


class HubResizeTest(_SurfaceCase):
    async def test_every_hub_keeps_its_selected_row(self) -> None:
        for label, hub in self.hubs():
            with self.subTest(hub=label):
                app = create_app(str(self.store.path))
                async with app.run_test(size=SIZES[0]) as pilot:
                    await pilot.pause()
                    app.push_screen(hub)
                    await pilot.pause()
                    highlighted = hub.query_one("#hub-list").highlighted
                    body = str(hub.query_one("#hub-preview-body", Static).content)

                    def current(node: Any = hub) -> Any:
                        return node.query_one("#hub-list").highlighted

                    matrix = await ResizeMatrix(label).walk(
                        pilot,
                        parts=HUB_PARTS,
                        selection=current,
                        scrolls=("#hub-preview", "#hub-list-wrap"),
                        cursors=("#hub-list",),
                    )
                    self.assertEqual(matrix.sizes(), SIZES)
                    for snapshot in matrix.snapshots:
                        self.assertEqual(snapshot.selection, highlighted)
                        self.assertEqual(snapshot.cursor["#hub-list"], highlighted)
                        scroll, maximum = snapshot.scroll["#hub-preview"]
                        self.assertLessEqual(scroll, maximum)
                    self.assertEqual(hub.query_one("#hub-list").highlighted, highlighted)
                    self.assertEqual(str(hub.query_one("#hub-preview-body", Static).content), body)

    async def test_every_hub_split_fits_the_screen(self) -> None:
        for label, hub in self.hubs():
            with self.subTest(hub=label):
                app = create_app(str(self.store.path))
                async with app.run_test(size=SIZES[0]) as pilot:
                    await pilot.pause()
                    app.push_screen(hub)
                    await pilot.pause()
                    matrix = await ResizeMatrix(label).walk(pilot, parts=HUB_PARTS)
                    for snapshot in matrix.snapshots:
                        snapshot.assert_inside(self)
                        snapshot.assert_no_overlap(self, ("list", "preview"))

    async def test_every_hub_keeps_its_size_classes_current(self) -> None:
        for label, hub in self.hubs():
            with self.subTest(hub=label):
                app = create_app(str(self.store.path))
                async with app.run_test(size=SIZES[0]) as pilot:
                    await pilot.pause()
                    app.push_screen(hub)
                    await pilot.pause()
                    for width, height in SIZES:
                        await pilot.resize_terminal(width, height)
                        await pilot.pause()
                        self.assertEqual(hub.has_class("compact"), width < 80, f"{label} {width}")
                        self.assertEqual(hub.has_class("wide"), width >= 120, f"{label} {width}")


class SourceAndDiffResizeTest(_SurfaceCase):
    async def test_the_source_screen_reflows_and_keeps_its_cursor(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            screen = SourceScreen(self.store, "plan", self.plan.id)
            app.push_screen(screen)
            await pilot.pause(0.3)
            cursor = screen.query_one("#source-tree").cursor_node
            matrix = await ResizeMatrix("source").walk(
                pilot,
                parts=SOURCE_PARTS,
                scrolls=("#source-preview", "#source-tree-wrap"),
                cursors=("#source-tree",),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                snapshot.assert_inside(self)
                self.assertIs(screen.query_one("#source-tree").cursor_node, cursor)
                if snapshot.size[0] < 100:
                    tree = snapshot.part("tree").region
                    preview = snapshot.part("preview").region
                    self.assertEqual(tree[0], preview[0])
                    self.assertLess(tree[1], preview[1])
                else:
                    tree = snapshot.part("tree").region
                    preview = snapshot.part("preview").region
                    self.assertEqual(tree[1], preview[1])
                    self.assertLess(tree[0], preview[0])

    async def test_the_source_screen_keeps_its_diff_page(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = SourceScreen(self.store, "plan", self.plan.id)
            app.push_screen(screen)
            await pilot.pause(0.4)
            tree = screen.query_one("#source-tree")
            for _ in range(40):
                if tree.root.children:
                    break
                await pilot.pause(0.05)
            self.assertTrue(tree.root.children)
            tree.move_cursor(tree.root.children[0])
            await pilot.pause()
            screen._view.page_offset = 300
            screen._view.page_has_more = True
            for width, height in ((40, 24), (80, 24), (120, 40), (160, 50)):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(screen._view.page_offset, 300, f"page at {width}")

    async def test_the_plan_diff_reflows_and_keeps_its_page(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            app.push_screen(PlanDiffScreen(DIFF))
            await pilot.pause()
            screen = app.screen
            matrix = await ResizeMatrix("plan diff").walk(
                pilot,
                parts=DIFF_PARTS,
                scrolls=("#plan-diff-scroll",),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                snapshot.assert_inside(self)
                snapshot.assert_unclipped(self, ("body",))
                scroll, maximum = snapshot.scroll["#plan-diff-scroll"]
                self.assertLessEqual(scroll, maximum)
                self.assertIn(
                    "TASKS",
                    str(screen.query_one("#plan-diff-body", Static).content),
                )

    async def test_the_plan_diff_restores_its_page_after_resize(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.push_screen(PlanDiffScreen(DIFF))
            await pilot.pause()
            scroll = app.screen.query_one("#plan-diff-scroll")
            scroll.scroll_to(y=4, animate=False)
            await pilot.pause()
            for width, height in ((40, 24), (160, 50), (80, 24)):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                await pilot.pause()
                self.assertEqual(scroll.scroll_y, min(4, scroll.max_scroll_y), f"page at {width}")


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupResizeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.db = str(base / "setup.db")
        sandbox_home(self, self.home)

    def session(self) -> Any:
        from lazyplan.infrastructure.host_models import HostCatalog

        def catalogs(hosts: Any, _home: Any, _root: Any) -> dict[str, HostCatalog]:
            return {
                host: HostCatalog(
                    host=host,
                    label=host.title(),
                    models=("tiny", "large"),
                    tier_defaults={"fast": "tiny", "standard": "tiny", "deep": "large"},
                )
                for host in hosts
            }

        return setup.SetupSession.load(self.repo, self.home, "1.0", discover=catalogs)

    async def test_the_setup_wizard_reflows_at_every_size(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            app.push_screen(SetupWizardScreen(self.session()))
            await pilot.pause()
            screen = app.screen
            matrix = await ResizeMatrix("setup").walk(
                pilot,
                parts={
                    "page": "#setup-page",
                    "head": "#setup-head",
                    "rail": "#setup-rail",
                    "content": "#setup-content",
                    "hints": "#setup-hints",
                    "actions": "#setup-actions",
                },
                scrolls=("#setup-content",),
            )
            self.assertEqual(matrix.sizes(), SIZES)
            for snapshot in matrix.snapshots:
                with self.subTest(size=snapshot.size):
                    snapshot.assert_inside(self)
                    if snapshot.size[0] < 80:
                        self.assertIsNone(snapshot.part("rail").region)
                    else:
                        self.assertIsNotNone(snapshot.part("rail").region)
                        snapshot.assert_no_overlap(self, ("rail", "content"))
            for width, height in SIZES:
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                self.assertEqual(screen.has_class("compact"), width < 80, f"compact {width}")
                self.assertEqual(screen.has_class("wide"), width >= 120, f"wide {width}")
                self.assertEqual(screen.has_class("short"), height < 30, f"short {height}")
                self.assertEqual(
                    screen.query_one("#setup-rail").display, width >= 80, f"rail {width}"
                )


class ModalResizeTest(_SurfaceCase):
    async def test_every_modal_fits_and_keeps_focus(self) -> None:
        for label, factory, selector in MODALS:
            with self.subTest(modal=label):
                app = create_app(str(self.store.path))
                async with app.run_test(size=SIZES[0]) as pilot:
                    await pilot.pause()
                    app.push_screen(factory())
                    await pilot.pause()
                    dialog = app.screen.query_one(selector)
                    for width, height in SIZES:
                        await pilot.resize_terminal(width, height)
                        await pilot.pause()
                        region = dialog.region
                        self.assertGreaterEqual(region.x, 0)
                        self.assertGreaterEqual(region.y, 0)
                        self.assertLessEqual(region.x + region.width, width)
                        self.assertLessEqual(region.y + region.height, height)
                        focused = app.focused
                        if focused is not None:
                            self.assertIn(dialog, focused.ancestors)

    @unittest.expectedFailure
    async def test_every_form_reapplies_its_size_classes(self) -> None:
        for label, factory in FORM_MODALS:
            with self.subTest(modal=label):
                app = create_app(str(self.store.path))
                async with app.run_test(size=SIZES[0]) as pilot:
                    await pilot.pause()
                    screen = factory()
                    app.push_screen(screen)
                    await pilot.pause()
                    for width, height in SIZES:
                        await pilot.resize_terminal(width, height)
                        await pilot.pause()
                        self.assertEqual(screen.has_class("compact"), width < 80, label)
                        self.assertEqual(screen.has_class("wide"), width >= 120, label)
                        self.assertEqual(screen.has_class("short"), height < 30, label)

    async def test_the_export_picker_reapplies_its_size_classes(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=SIZES[0]) as pilot:
            await pilot.pause()
            screen = ExportScreen(self.store, self.plan.id, self.plan.name, default_dir=self.root)
            app.push_screen(screen)
            await pilot.pause()
            for width, height in SIZES:
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                self.assertEqual(screen.has_class("compact"), width < 80, f"export {width}")
                self.assertEqual(screen.has_class("wide"), width >= 120, f"export {width}")

    @unittest.expectedFailure
    async def test_the_palette_has_no_horizontal_overflow(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(PaletteScreen())
            await pilot.pause()
            matrix = await ResizeMatrix("palette").walk(
                pilot, parts={"dlg": "#dlg", "list": "#palette-list"}
            )
            for snapshot in matrix.snapshots:
                snapshot.assert_inside(self)
                snapshot.assert_unclipped(self, ("dlg",))

    @unittest.expectedFailure
    async def test_the_export_picker_has_no_horizontal_overflow(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(
                ExportScreen(self.store, self.plan.id, self.plan.name, default_dir=self.root)
            )
            await pilot.pause()
            matrix = await ResizeMatrix("export").walk(
                pilot, parts={"dlg": "#dlg", "tree": "#export-tree"}
            )
            for snapshot in matrix.snapshots:
                snapshot.assert_inside(self)
                snapshot.assert_unclipped(self, ("dlg", "tree"))


if __name__ == "__main__":
    unittest.main()
