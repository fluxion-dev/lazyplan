"""Placement, agents, hooks, and pointer steps edit the shared draft."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.host_models import HostCatalog
from lazyplan.presentation import setup
from tests.support.home import sandbox_home

try:
    from textual.widgets import Checkbox, OptionList, Select, Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import SetupWizardScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    SetupWizardScreen = None  # type: ignore[assignment]
    Checkbox = OptionList = Select = Static = None  # type: ignore[assignment,misc]


def _catalogs(hosts: Iterable[str], _home: Path, _root: Path | None) -> dict[str, HostCatalog]:
    return {host: HostCatalog(host=host, label=host.title()) for host in hosts}


@unittest.skipUnless(create_app is not None, "textual not installed")
class SetupWizardBasicsTest(unittest.IsolatedAsyncioTestCase):
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
        return setup.SetupSession.load(self.repo, self.home, "1.0", discover=_catalogs)

    async def offer(self, app: Any, pilot: Any, session: setup.SetupSession, start: str) -> Any:
        screen = SetupWizardScreen(session, start=start)
        app.push_screen(screen, lambda _result: None)
        await pilot.pause()
        return screen

    async def test_placement_offers_home_and_repo_with_their_tradeoffs(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "placement")
            listing = screen.query_one("#setup-placement-list", OptionList)
            self.assertEqual(listing.option_count, 2)
            text = "\n".join(str(choice.render()) for choice in screen.query(".setup-choice"))
            self.assertIn("Share with teammates", text)
            self.assertIn("Nothing is written into this checkout", text)

    async def test_choosing_repo_placement_moves_the_database_path(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "placement")
            listing = screen.query_one("#setup-placement-list", OptionList)
            listing.highlighted = _option_index(listing, "repo")
            listing.action_select()
            await pilot.pause()
            self.assertEqual(session.draft.placement, "repo")
            self.assertEqual(
                session.db_path.resolve(),
                (self.repo / ".agents" / "lazyplan" / "lazyplan.db").resolve(),
            )

    async def test_choosing_home_placement_returns_to_the_shared_database(self) -> None:
        session = self.session()
        session.set_placement("repo")
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "placement")
            listing = screen.query_one("#setup-placement-list", OptionList)
            listing.highlighted = _option_index(listing, "home")
            listing.action_select()
            await pilot.pause()
            self.assertEqual(session.draft.placement, "home")
            self.assertTrue(str(session.db_path).startswith(str(self.home)))

    async def test_toggling_a_host_selection_reaches_the_draft(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "agents")
            box = screen.query_one("#setup-agent-opencode", Checkbox)
            box.value = True
            await pilot.pause()
            self.assertIn("opencode", session.draft.agents)
            box.value = False
            await pilot.pause()
            self.assertNotIn("opencode", session.draft.agents)

    async def test_host_order_follows_the_registry_not_the_click_order(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "agents")
            screen.query_one("#setup-agent-claude", Checkbox).value = True
            await pilot.pause()
            screen.query_one("#setup-agent-opencode", Checkbox).value = True
            await pilot.pause()
            self.assertEqual(session.draft.agents, ["opencode", "claude"])

    async def test_turning_skills_off_hides_the_model_steps(self) -> None:
        session = self.session()
        session.set_agents(["opencode"])
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "agents")
            self.assertIn("models", [step.key for step in screen._steps])
            screen.query_one("#setup-skills", Checkbox).value = False
            await pilot.pause()
            self.assertFalse(session.draft.skills_enabled)
            keys = [step.key for step in screen._steps]
            self.assertNotIn("models", keys)
            self.assertNotIn("roles", keys)

    async def test_the_detection_hint_names_the_host_state(self) -> None:
        (self.home / ".claude").mkdir()
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "agents")
            label = str(screen.query_one("#setup-agent-claude", Checkbox).label)
            self.assertIn("detected", label)
            self.assertIn(str(self.home / ".claude"), label)

    async def test_hook_mode_changes_reach_the_draft(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            select = screen.query_one("#setup-hooks-mode", Select)
            select.value = "advisory"
            await pilot.pause()
            self.assertEqual(session.draft.hooks_mode, "advisory")
            select.value = "off"
            await pilot.pause()
            self.assertEqual(session.draft.hooks_mode, "off")

    async def test_the_pointer_toggle_reaches_the_draft(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            pointer = screen.query_one("#setup-pointer", Checkbox)
            self.assertFalse(pointer.disabled)
            pointer.value = True
            await pilot.pause()
            self.assertTrue(session.draft.agents_pointer)

    async def test_the_pointer_is_unavailable_with_repo_placement(self) -> None:
        session = self.session()
        session.set_placement("repo")
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            pointer = screen.query_one("#setup-pointer", Checkbox)
            self.assertTrue(pointer.disabled)
            self.assertFalse(session.draft.agents_pointer)

    async def test_the_pointer_is_unavailable_outside_a_checkout(self) -> None:
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        session = setup.SetupSession.load(outside, self.home, "1.0", discover=_catalogs)
        session.draft.placement = "home"
        session.root = None
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            pointer = screen.query_one("#setup-pointer", Checkbox)
            self.assertTrue(pointer.disabled)

    async def test_leaving_a_step_reports_invalid_values(self) -> None:
        session = self.session()
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            screen = await self.offer(app, pilot, session, "hooks")
            session.set_hooks_mode("sometimes")
            await pilot.press("n")
            await pilot.pause()
            self.assertEqual(screen.step.key, "hooks")
            errors = screen.query_one("#setup-errors", Static)
            self.assertTrue(errors.display)
            self.assertIn("hooks mode", str(errors.render()))


def _option_index(listing: OptionList, option_id: str) -> int:
    for index in range(listing.option_count):
        if str(listing.get_option_at_index(index).id) == option_id:
            return index
    raise AssertionError(f"missing option {option_id}")


if __name__ == "__main__":
    unittest.main()
