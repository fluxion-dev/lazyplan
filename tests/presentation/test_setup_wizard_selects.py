"""Closed wizard dropdowns paint their value and anchor their menu."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from html import unescape
from pathlib import Path
from typing import Any

from lazyplan.core.policies import effort as effort_policy
from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from lazyplan.presentation.setup.health import HealthFinding
from lazyplan.presentation.tui.screens.setup_support import (
    HOOK_MODES,
    INHERIT_LABEL,
)
from tests.support.home import sandbox_home

try:
    from textual.widgets import Select, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen
    from lazyplan.presentation.tui.widgets.setup_controls import widget_id
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = None  # type: ignore[assignment]
    Select = Static = None  # type: ignore[assignment,misc]

    def widget_id(text: str) -> str:  # pragma: no cover - textual not installed
        return text


WIDE = (120, 40)
COMPACT = (70, 24)
SELECT_STEPS = ("hooks", "models", "roles", "integrations", "appearance")


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=("acme-fast-1", "acme-standard-1", "acme-deep-1"),
        )
        for host in hosts
    }


def _checks(findings: tuple[HealthFinding, ...]) -> Any:
    return lambda: findings


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardSelectsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.home.mkdir()
        self.repo = base / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.db = str(base / "wizard.db")
        sandbox_home(self, self.home)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def session(self) -> setup.SetupSession:
        session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
        session.set_agents(["opencode"])
        session.set_hooks_mode(HOOK_MODES[1][0])
        session.set_tier_model("opencode", "fast", "acme-fast-1")
        session.set_role_tier("reviewer", "fast")
        session.set_role_effort("reviewer", effort_policy.HIGH)
        return session

    async def offer(self, app: Any, pilot: Any, session: setup.SetupSession, start: str) -> Any:
        screen = SetupWizardScreen(session, start=start, checks=_checks(()))
        app.push_screen(screen, lambda _result: None)
        await pilot.pause()
        return screen

    def screen_text(self, app: Any) -> str:
        """The painted screen, with SVG escapes and non-breaking spaces undone."""
        return unescape(app.export_screenshot()).replace("\xa0", " ")

    def label_text(self, select: Any) -> str:
        return str(select.query_one("#label", Static).render()).strip()

    def assert_control_fits(self, select: Any, text: str, step: str, viewport: Any) -> None:
        """The inner control owns the full field box, so its label paints."""
        current = select.query_one("SelectCurrent")
        box = select.content_region
        inner = current.region
        self.assertGreaterEqual(inner.x, box.x)
        self.assertGreaterEqual(inner.y, box.y)
        self.assertLessEqual(inner.right, box.right, step)
        self.assertLessEqual(inner.bottom, box.bottom, step)
        label = self.label_text(select)
        self.assertNotEqual(label, "")
        self.assertNotEqual(label, select.prompt)
        if viewport.contains_region(select.region):
            self.assertTrue(label in text, f"{step}: {label!r} missing from the painted screen")

    async def assert_step_selects(self, app: Any, pilot: Any, session: setup.SetupSession) -> None:
        for start in SELECT_STEPS:
            screen = await self.offer(app, pilot, session, start)
            selects = list(screen.query("#setup-panel Select"))
            self.assertTrue(selects, start)
            text = self.screen_text(app)
            viewport = screen.query_one("#setup-content").content_region
            for select in selects:
                self.assert_control_fits(select, text, start, viewport)
            app.pop_screen()
            await pilot.pause()

    async def test_every_select_shows_its_value_at_wide_size(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            await self.assert_step_selects(app, pilot, session)

    async def test_every_select_shows_its_value_at_compact_size(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=COMPACT) as pilot:
            await self.assert_step_selects(app, pilot, session)

    async def test_default_choices_paint_their_labels(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            text = self.screen_text(app)
            select = screen.query_one("#setup-hooks-mode", Select)
            self.assertEqual(self.label_text(select), HOOK_MODES[1][1])
            self.assertIn(HOOK_MODES[1][1], text)

            app.pop_screen()
            screen = await self.offer(app, pilot, session, "models")
            text = self.screen_text(app)
            self.assertIn("acme-fast-1", text)
            self.assertEqual(
                self.label_text(screen.query_one("#setup-tier-opencode-fast", Select)),
                "acme-fast-1",
            )
            self.assertEqual(
                self.label_text(screen.query_one("#setup-tier-opencode-deep", Select)),
                INHERIT_LABEL,
            )

            app.pop_screen()
            screen = await self.offer(app, pilot, session, "integrations")
            text = self.screen_text(app)
            first = session.pending[0]
            select = screen.query_one(f"#setup-integration-{widget_id(first.id)}", Select)
            self.assertIn(str(select.query_one("#label", Static).render()).strip(), text)

    async def test_the_menu_opens_flush_under_the_control(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            overlay = select.query_one("SelectOverlay")
            select.focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(select.expanded)
            self.assertTrue(overlay.display)
            self.assertEqual(overlay.region.y, select.region.bottom)
            self.assertEqual(overlay.region.x, select.region.x)
            self.assertEqual(overlay.region.width, select.region.width)

    async def test_a_click_opens_the_closed_control(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            point = select.region
            await pilot.click(offset=(point.x + 4, point.y + 1))
            await pilot.pause()
            self.assertTrue(select.expanded)
            self.assertTrue(select.query_one("SelectOverlay").display)

    async def test_keyboard_selection_updates_the_draft_and_the_label(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            select.focus()
            await pilot.press("enter")
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(session.draft.hooks_mode, HOOK_MODES[2][0])
            self.assertEqual(self.label_text(select), HOOK_MODES[2][1])
            self.assertIn(HOOK_MODES[2][1], self.screen_text(app))

    async def test_a_wrapped_value_sizes_its_field(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(100, 30)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            select = screen.query_one("#setup-tier-opencode-deep", Select)
            current = select.query_one("SelectCurrent")
            self.assertGreater(current.region.height, 3)
            self.assertEqual(select.content_region.height, current.region.height)
            self.assertIn("inherit (host", self.screen_text(app))
            overlay = select.query_one("SelectOverlay")
            select.focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(overlay.display)
            self.assertTrue(screen.region.contains_region(overlay.region))

    async def test_a_value_survives_a_step_round_trip(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=WIDE) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            select.value = HOOK_MODES[2][0]
            await pilot.pause()
            app.pop_screen()
            await pilot.pause()

            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            self.assertEqual(select.value, HOOK_MODES[2][0])
            self.assertEqual(self.label_text(select), HOOK_MODES[2][1])
            self.assertIn(HOOK_MODES[2][1], self.screen_text(app))
