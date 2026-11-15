"""Every full-screen bottom bar pins the running version."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

from lazyplan.core.entities import PlanRevision

try:
    from lazyplan.infrastructure.host_models import HostCatalog
    from lazyplan.presentation import setup
    from lazyplan.presentation.cli.parser import package_version
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import UpdateScreen
    from lazyplan.presentation.tui.screens.maintenance import MaintenanceScreen
    from lazyplan.presentation.tui.screens.plan_diff import PlanDiffScreen
    from lazyplan.presentation.tui.screens.setup import SetupWizardScreen
    from lazyplan.presentation.tui.screens.source import SourceScreen
    from lazyplan.presentation.tui.widgets.taskbar import Taskbar
    from lazyplan.services.revisions import DiffResult
    from lazyplan.store import Store

    _TEXTUAL_OK = True
except ImportError as exc:  # pragma: no cover - textual not installed
    raise unittest.SkipTest(f"textual not installed: {exc}") from None

from tests.support.home import sandbox_home

REVISION = PlanRevision(
    id=1,
    plan_id=1,
    revision=1,
    approved_at=0.0,
    digest="b" * 64,
    snapshot="{}",
)
EMPTY_DIFF = DiffResult(
    plan_id=1,
    from_revision=REVISION,
    to_revision=None,
    entries=(),
    summary={"add": 0, "remove": 0, "change": 0, "move": 0, "total": 0},
)


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {host: HostCatalog(host=host, label=host.title()) for host in hosts}


class TaskbarBarsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        sandbox_home(self, self.home)
        self.store = Store(str(base / "plans.db"))
        plan = self.store.add_plan("Taskbar")
        milestone = self.store.add_milestone(plan.id, "Slice")
        self.task = self.store.add_task(milestone.id, "Read the bar")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def assert_bar(self, app: object, pilot: object, bar_id: str) -> None:
        await pilot.pause(0.3)
        bar = app.screen.query_one(f"#{bar_id}", Taskbar)
        text = str(bar.render())
        self.assertTrue(text.endswith(f"v{package_version()}"), text)

    def sizes(self) -> tuple[tuple[int, int], ...]:
        return ((120, 40), (80, 24))

    async def test_the_hub_bar_shows_the_version(self) -> None:
        for size in self.sizes():
            app = create_app(str(self.store.path))
            async with app.run_test(size=size) as pilot:
                app.push_screen(MaintenanceScreen(self.store))
                await self.assert_bar(app, pilot, "hub-hints")

    async def test_the_plan_diff_bar_shows_the_version(self) -> None:
        for size in self.sizes():
            app = create_app(str(self.store.path))
            async with app.run_test(size=size) as pilot:
                app.push_screen(PlanDiffScreen(EMPTY_DIFF))
                await self.assert_bar(app, pilot, "plan-diff-hints")

    async def test_the_source_bar_shows_the_version(self) -> None:
        for size in self.sizes():
            app = create_app(str(self.store.path))
            async with app.run_test(size=size) as pilot:
                app.push_screen(SourceScreen(self.store, "task", self.task.id))
                await self.assert_bar(app, pilot, "source-hints")

    async def test_the_setup_bar_shows_the_version(self) -> None:
        for size in self.sizes():
            session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
            app = create_app(str(self.store.path))
            async with app.run_test(size=size) as pilot:
                app.push_screen(SetupWizardScreen(session))
                await self.assert_bar(app, pilot, "setup-hints")

    async def test_clicking_a_plan_diff_badge_opens_updates(self) -> None:
        app = create_app(str(self.store.path))
        async with app.run_test(size=(120, 40)) as pilot:
            app.push_screen(PlanDiffScreen(EMPTY_DIFF))
            await pilot.pause(0.3)
            app.update_controller.latest = "99.0.0"
            app.refresh_taskbar()
            await pilot.pause()
            bar = app.screen.query_one("#plan-diff-hints", Taskbar)
            await pilot.click(bar, offset=(bar.size.width - 2, 0))
            await pilot.pause()
            self.assertIsInstance(app.screen, UpdateScreen)
