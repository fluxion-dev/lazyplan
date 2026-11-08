"""Provenance hubs: source cross-links, pull requests, and activity."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.store import Store
from tests.support.pilot import settle

try:
    from textual.widgets import Button, Input, OptionList

    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens.detail import DetailScreen
    from lazyplan.presentation.tui.screens.forms import FilterPromptScreen
    from lazyplan.presentation.tui.screens.hub_provenance import ActivityHub, PullRequestHub
    from lazyplan.presentation.tui.screens.source import SourceScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(
    tui_mod is not None and getattr(tui_mod, "_TEXTUAL_OK", False), "textual not installed"
)
class ProvenanceHubTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "prov.db")
        store = Store(self.db)
        self.plan = store.add_plan("Provenance", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.")
        self.task = store.add_task(self.milestone.id, "Ship it", "Commit: one.")
        self.store = Store(self.db)
        self.store.link_commit(
            "task",
            self.task.id,
            "a" * 40,
            subject="ship it",
            author="Tester",
            repo_root=self.tmp.name,
            files=("src/app.py",),
        )
        self.store.link_forge(
            "task",
            self.task.id,
            7,
            url="https://github.com/org/repo/pull/7",
            title="Fix login",
            state="merged",
            checks="pass",
            reviews="approved",
            base_ref="main",
            head_ref="feat/login",
        )
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_pull_request_hub_lists_state_and_links_a_url(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(PullRequestHub(self.store, "task", self.task.id))
            await pilot.pause()
            options = self.app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 1)
            preview = str(self.app.screen.query_one("#hub-preview-body").render())
            self.assertIn("checks   pass", preview)
            self.assertIn("reviews approved", preview)
            self.assertIn("base     main", preview)
            await pilot.press("a")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            self.app.screen.query_one(
                "#filter-input", Input
            ).value = "https://github.com/org/repo/pull/9"
            await pilot.press("enter")
            await pilot.pause()
            links = self.store.list_forge_links("task", self.task.id)
            self.assertEqual({link.number for link in links}, {7, 9})

    async def test_pull_request_refresh_is_the_only_network_path(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(PullRequestHub(self.store, "task", self.task.id))
            await pilot.pause()
            with mock.patch(
                "lazyplan.presentation.tui.screens.hub_provenance.services.refresh_forge",
                return_value={"linked": 1, "stale": 0},
            ) as refreshed:
                await pilot.press("r")
                await pilot.pause()
                await self.app.workers.wait_for_complete()
                await settle(pilot)
                refreshed.assert_called_once_with(self.store, "task", self.task.id, actor="tui")

    async def test_pull_request_hub_unlinks_and_opens(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(PullRequestHub(self.store, "task", self.task.id))
            await pilot.pause()
            with mock.patch(
                "lazyplan.presentation.tui.screens.hub_provenance.webbrowser.open"
            ) as opened:
                await pilot.press("o")
                await pilot.pause()
                opened.assert_called_once_with("https://github.com/org/repo/pull/7")
            await pilot.press("d")
            await pilot.pause()
            self.app.screen.query_one("#ok", Button).press()
            await pilot.pause()
            self.assertEqual(self.store.list_forge_links("task", self.task.id), [])

    async def test_activity_hub_filters_and_opens_the_target(self) -> None:
        self.store.log("alice", "task", "status", f"task #{self.task.id} -> doing")
        self.store.log("tui", "override", "status", f"task #{self.task.id}: status — manual")
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(ActivityHub(self.store))
            await pilot.pause()
            options = self.app.screen.query_one("#hub-list", OptionList)
            self.assertGreaterEqual(options.option_count, 2)
            await pilot.press("u")
            await pilot.pause()
            self.assertEqual(options.option_count, 1)
            await pilot.press("u")
            await pilot.pause()
            self.assertGreaterEqual(options.option_count, 2)
            await pilot.press("f")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            self.app.screen.query_one("#filter-input", Input).value = "alice"
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(options.option_count, 1)
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)

    async def test_activity_hub_kind_filter(self) -> None:
        self.store.log("alice", "task", "status", f"task #{self.task.id} -> doing")
        self.store.log("tui", "override", "status", f"task #{self.task.id}: status — manual")
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(ActivityHub(self.store))
            await pilot.pause()
            await pilot.press("K")
            await pilot.pause()
            self.app.screen.query_one("#filter-input", Input).value = "override"
            await pilot.press("enter")
            await pilot.pause()
            options = self.app.screen.query_one("#hub-list", OptionList)
            self.assertEqual(options.option_count, 1)

    async def test_source_enter_opens_the_owning_row(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.push_screen(SourceScreen(self.store, "task", self.task.id))
            await pilot.pause()
            await self.app.workers.wait_for_complete()
            await settle(pilot)
            tree = self.app.screen.query_one("#source-tree")
            repo = tree.root.children[0]
            tree.move_cursor(repo.children[0])
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, DetailScreen)
            self.assertEqual(self.app.screen.dkind, "task")
            self.assertEqual(self.app.screen.doid, self.task.id)


if __name__ == "__main__":
    unittest.main()
