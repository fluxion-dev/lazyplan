"""The notification log opens by key and palette from every full-screen view."""

from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

from lazyplan.core.entities import PlanRevision

try:
    from textual.widgets import Input

    from lazyplan.infrastructure.host_models import HostCatalog
    from lazyplan.presentation import setup
    from lazyplan.presentation.shared import registry
    from lazyplan.presentation.shared.palette import by_id as command_by_id
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.hub import HubScreen
    from lazyplan.presentation.tui.screens.notification_log import NotificationLogScreen
    from lazyplan.presentation.tui.screens.plan_diff import PlanDiffScreen
    from lazyplan.presentation.tui.screens.setup import SetupWizardScreen
    from lazyplan.presentation.tui.screens.source import SourceScreen
    from lazyplan.services.revisions import DiffResult
    from lazyplan.store import Store
    from tests.support.home import sandbox_home

    _TEXTUAL_OK = True
except ImportError as exc:  # pragma: no cover - textual not installed
    raise unittest.SkipTest(f"textual not installed: {exc}") from None

NO_UPDATE = mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"})

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


class NotificationAccessTest(unittest.IsolatedAsyncioTestCase):
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
        plan = self.store.add_plan("Log access")
        milestone = self.store.add_milestone(plan.id, "Slice")
        self.task = self.store.add_task(milestone.id, "Open the log")
        self.plan_id = plan.id

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def push_main(self, app) -> None:
        """The main shell needs no push."""

    def push_diff(self, app) -> None:
        app.push_screen(PlanDiffScreen(EMPTY_DIFF))

    def push_source(self, app) -> None:
        app.push_screen(SourceScreen(self.store, "task", self.task.id))

    def push_setup(self, app) -> None:
        session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
        app.push_screen(SetupWizardScreen(session))

    def push_hub(self, app) -> None:
        from lazyplan.presentation.tui.screens.hub_kinds import QuestionsHub

        app.push_screen(QuestionsHub(self.store, self.plan_id))

    async def open_with_key(self, push) -> None:
        with NO_UPDATE:
            app = create_app(str(self.store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                push(app)
                await pilot.pause()
                await pilot.press("L")
                await pilot.pause()
                self.assertIsInstance(app.screen, NotificationLogScreen)

    async def open_with_palette(self, push) -> None:
        with NO_UPDATE:
            app = create_app(str(self.store.path))
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                push(app)
                await pilot.pause()
                await pilot.press("c")
                await pilot.pause()
                field = app.screen.query_one("#palette-input", Input)
                field.value = "notification log"
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                self.assertIsInstance(app.screen, NotificationLogScreen)

    async def test_l_opens_from_the_main_shell(self) -> None:
        await self.open_with_key(self.push_main)

    async def test_l_opens_from_a_hub(self) -> None:
        await self.open_with_key(self.push_hub)

    async def test_l_opens_from_the_source_trail(self) -> None:
        await self.open_with_key(self.push_source)

    async def test_l_opens_from_the_plan_diff(self) -> None:
        await self.open_with_key(self.push_diff)

    async def test_l_opens_from_setup(self) -> None:
        await self.open_with_key(self.push_setup)

    async def test_the_palette_opens_from_the_main_shell(self) -> None:
        await self.open_with_palette(self.push_main)

    async def test_the_palette_opens_from_a_hub(self) -> None:
        await self.open_with_palette(self.push_hub)

    async def test_the_palette_opens_from_the_source_trail(self) -> None:
        await self.open_with_palette(self.push_source)

    async def test_the_palette_opens_from_the_plan_diff(self) -> None:
        await self.open_with_palette(self.push_diff)

    async def test_the_palette_opens_from_setup(self) -> None:
        await self.open_with_palette(self.push_setup)


class NotificationAccessRegistryTest(unittest.TestCase):
    def test_the_registry_names_the_log_command_and_key(self) -> None:
        command = command_by_id("notification-log")
        self.assertIsNotNone(command)
        self.assertEqual(command.action_id, "app.log")
        self.assertEqual(command.key, "L")
        self.assertEqual(command.screens, ("any",))
        action = registry.by_id("app.log")
        self.assertIsNotNone(action)
        self.assertEqual(action.key, "L")
        self.assertEqual(action.surfaces, ("tui",))

    def test_the_palette_enables_the_log_on_every_screen(self) -> None:
        for screen in ("tree", "hub", "source", "setup", "form", "log"):
            with self.subTest(screen=screen):
                context = registry.palette_context(registry.Context(screen=screen))
                self.assertIsNone(context["notification-log"])

    def test_the_log_key_does_not_shadow_hub_unrelate(self) -> None:
        bindings = {binding.key: binding.action for binding in HubScreen.BINDINGS}
        self.assertEqual(bindings.get("X"), "unrelate")
        self.assertNotIn("L", bindings)


if __name__ == "__main__":
    unittest.main()
