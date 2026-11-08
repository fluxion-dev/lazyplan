"""Trust and coordination QA: reachability and clean cancels."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.shared.palette import by_id
from lazyplan.store import Store

try:
    from lazyplan.presentation import tui as tui_mod
    from lazyplan.presentation.tui.screens import FilterPromptScreen, ProveScreen
except ImportError:  # pragma: no cover - stdlib-only interpreter
    tui_mod = None  # type: ignore[assignment]

from tests.support.pilot import settle

TRUST_COMMANDS = (
    "approve-plan",
    "plan-diff",
    "prove-criterion",
    "add-question",
    "resolve-question",
    "reopen-question",
    "link-ref",
    "unlink-ref",
    "claim-task",
    "block-task",
    "unblock-task",
    "finish-task",
)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TrustQaTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "trust.db")
        store = Store(self.db)
        self.plan = store.add_plan("Trust plan", "What", goal="Why")
        self.milestone = store.add_milestone(self.plan.id, "M", "As a user.", actor="t")
        self.task = store.add_task(self.milestone.id, "T", "Commit: one.", actor="t")
        store.add_criteria("task", self.task.id, "Works", actor="t")
        self.store = store
        self.app = tui_mod.create_app(self.db)
        self.app.override_mode = True

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def test_all_trust_commands_are_registered(self) -> None:
        for command_id in TRUST_COMMANDS:
            with self.subTest(command=command_id):
                command = by_id(command_id)
                self.assertIsNotNone(command)
                assert command is not None
                self.assertTrue(command.in_palette)

    async def test_detail_opens_evidence_and_question_forms(self) -> None:
        async with self.app.run_test(size=(120, 40)) as pilot:
            await settle(pilot)
            self.app.selected = ("task", self.task.id)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ProveScreen)
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("Q")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, FilterPromptScreen)
            await pilot.press("escape")
            await pilot.pause()

    async def test_cancelled_finish_override_leaves_the_task_unchanged(self) -> None:
        with mock.patch(
            "lazyplan.services.finish_task",
            side_effect=services.GateError("task #1 needs passing evidence"),
        ):
            async with self.app.run_test(size=(120, 40)) as pilot:
                await settle(pilot)
                self.app.selected = ("task", self.task.id)
                await pilot.press("c")
                await pilot.pause()
                for char in "finish task":
                    await pilot.press(char)
                await pilot.press("enter")
                await pilot.pause()
                await pilot.pause()
                self.assertIsInstance(self.app.screen, FilterPromptScreen)
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(Store(self.db).get_task(self.task.id).status, Status.TODO)
                events = [event for event in Store(self.db).feed() if event["kind"] == "override"]
                self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
