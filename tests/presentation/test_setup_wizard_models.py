"""Model targets and role effort selectors edit the setup draft."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from tests.support.home import sandbox_home

try:
    from textual.widgets import Button, Input, Select, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen
    from lazyplan.presentation.tui.screens.setup import INHERIT
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = None  # type: ignore[assignment]
    INHERIT = "__inherit__"
    Button = Input = Select = Static = None  # type: ignore[assignment,misc]


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=("tiny", "large"),
            tier_defaults={"fast": "tiny", "standard": "tiny", "deep": "large"},
            source="config",
            warning="catalog unavailable, using defaults" if host == "claude" else "",
        )
        for host in hosts
    }


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardModelsTest(unittest.IsolatedAsyncioTestCase):
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

    def session(self, hosts: list[str] | None = None) -> setup.SetupSession:
        session = setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)
        session.set_agents(hosts if hosts is not None else ["opencode", "claude"])
        return session

    async def offer(self, app: Any, pilot: Any, session: setup.SetupSession, start: str) -> Any:
        screen = SetupWizardScreen(session, start=start)
        app.push_screen(screen, lambda _result: None)
        await pilot.pause()
        return screen

    async def test_model_rows_start_from_the_discovered_defaults(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            select = screen.query_one("#setup-tier-opencode-fast", Select)
            self.assertEqual(select.value, "tiny")
            entry = screen.query_one("#setup-model-opencode-fast", Input)
            self.assertEqual(entry.value, "tiny")

    async def test_choosing_a_catalog_model_updates_the_draft(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            screen.query_one("#setup-tier-opencode-fast", Select).value = "large"
            await pilot.pause()
            self.assertEqual(session.draft.tiers_map["fast"]["opencode"], "large")
            entry = screen.query_one("#setup-model-opencode-fast", Input)
            self.assertEqual(entry.value, "large")

    async def test_inherit_clears_the_tier_target(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            screen.query_one("#setup-tier-opencode-deep", Select).value = INHERIT
            await pilot.pause()
            self.assertEqual(session.draft.tiers_map["deep"]["opencode"], "")
            self.assertEqual(screen.query_one("#setup-model-opencode-deep", Input).value, "")

    async def test_a_manual_model_id_is_stored_on_submit(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            entry = screen.query_one("#setup-model-opencode-fast", Input)
            entry.value = "provider/tiny-custom"
            entry.focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(session.draft.tiers_map["fast"]["opencode"], "provider/tiny-custom")

    async def test_a_typed_model_is_kept_when_leaving_the_step(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            screen.query_one("#setup-model-opencode-fast", Input).value = "typed/later"
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(session.draft.tiers_map["fast"]["opencode"], "typed/later")

    async def test_the_catalog_source_and_warning_are_visible(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "models")
            text = "\n".join(str(item.render()) for item in screen.query(".setup-note"))
            self.assertIn("source: config", text)
            self.assertIn("catalog unavailable", text)

    async def test_role_tier_selectors_update_the_profile(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            screen.query_one("#setup-role-tier-reviewer", Select).value = "fast"
            await pilot.pause()
            self.assertEqual(session.draft.profiles_map["reviewer"].tier, "fast")

    async def test_effort_stores_a_curated_level(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            screen.query_one("#setup-role-effort-scout", Select).value = "high"
            await pilot.pause()
            self.assertEqual(session.draft.profiles_map["scout"].effort, "high")

    async def test_effort_is_enabled_when_a_host_supports_it(self) -> None:
        session = self.session(["opencode"])
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            effort = screen.query_one("#setup-role-effort-scout", Select)
            self.assertFalse(effort.disabled)

    async def test_effort_is_disabled_when_no_host_supports_it(self) -> None:
        session = self.session(["gemini"])
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            effort = screen.query_one("#setup-role-effort-scout", Select)
            self.assertTrue(effort.disabled)
            self.assertEqual(session.draft.profiles_map["scout"].effort, "")

    async def test_reset_restores_default_tiers_and_clears_effort(self) -> None:
        session = self.session()
        session.set_role_tier("reviewer", "standard")
        session.set_role_effort("reviewer", "high")
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            screen.query_one("#setup-roles-reset", Button).press()
            await pilot.app.workers.wait_for_complete()
            await pilot.pause(0.2)
            self.assertEqual(session.draft.profiles_map["reviewer"].tier, "deep")
            self.assertEqual(session.draft.profiles_map["reviewer"].effort, "")
            self.assertEqual(session.draft.profiles_map["scout"].tier, "fast")
            tier = screen.query_one("#setup-role-tier-reviewer", Select)
            for _ in range(40):
                if tier.value == "deep":
                    break
                await pilot.pause(0.05)
            self.assertEqual(tier.value, "deep")

    async def test_a_stored_non_level_effort_stays_readable_until_edited(self) -> None:
        session = self.session()
        profile = session.draft.profiles_map["scout"]
        session.draft.profiles_map["scout"] = replace(profile, effort="legacy-value")
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "roles")
            notes = "\n".join(str(item.render()) for item in screen.query(".setup-note"))
            self.assertIn("legacy-value", notes)
            effort = screen.query_one("#setup-role-effort-scout", Select)
            self.assertEqual(effort.value, "")
            effort.value = "low"
            await pilot.pause()
            self.assertEqual(session.draft.profiles_map["scout"].effort, "low")


if __name__ == "__main__":
    unittest.main()
