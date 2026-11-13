"""The plan diff screen paints grouped changes and an in-sync state."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import services
from lazyplan.core.entities import PlanRevision
from lazyplan.core.policies.revisions import Change
from lazyplan.services.revisions import DiffEntry, DiffResult

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.plan_diff import PlanDiffScreen
    from lazyplan.store import Store
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    PlanDiffScreen = None  # type: ignore[assignment]
    Store = None  # type: ignore[assignment]

REVISION = PlanRevision(
    id=1,
    plan_id=1,
    revision=2,
    approved_at=0.0,
    digest="b" * 64,
    snapshot="{}",
)


def _result(entries: tuple[DiffEntry, ...]) -> DiffResult:
    return DiffResult(
        plan_id=1,
        from_revision=REVISION,
        to_revision=None,
        entries=entries,
        summary={
            "add": 0,
            "remove": 0,
            "change": len(entries),
            "move": 0,
            "total": len(entries),
        },
    )


DRIFT = _result(
    (
        DiffEntry(
            change=Change(
                kind="task",
                action="change",
                obj_id=7,
                identity="task:7",
                title="Read the diff",
                before="old scope",
                after="new scope",
            ),
            reason="scope clarified",
        ),
    )
)


@unittest.skipUnless(create_app is not None, "textual not installed")
class PlanDiffScreenTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(os.path.join(self.tmp.name, "plan.db"))
        self.plan = self.store.add_plan("Diff")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Read the diff")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def _open(self, result: DiffResult) -> tuple[object, str, str]:
        app = create_app(str(self.store.path))
        screen = PlanDiffScreen(result)
        async with app.run_test(size=(130, 35)) as pilot:
            app.push_screen(screen)
            await pilot.pause()
            head = str(app.screen.query_one("#plan-diff-head").content)
            body = str(app.screen.query_one("#plan-diff-body").content)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotEqual(app.screen, screen)
        return screen, head, body

    async def test_drift_paints_groups_and_changes(self) -> None:
        _, head, body = await self._open(DRIFT)
        self.assertIn("P1 scope diff", head)
        self.assertIn("1 changes", head)
        self.assertIn("TASKS", body)
        self.assertIn("task 7", body)
        self.assertIn("− old scope", body)
        self.assertIn("+ new scope", body)
        self.assertIn("reason: scope clarified", body)

    async def test_clean_plan_paints_in_sync(self) -> None:
        _, head, body = await self._open(_result(()))
        self.assertIn("0 changes", head)
        self.assertIn("in sync with the approved revision", body)

    async def test_plan_diff_action_opens_from_plan_and_task(self) -> None:
        services.approve(self.store, self.plan.id, actor="test", reason="start")
        self.store.update_task(self.task.id, title="Renamed task", actor="test")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            await pilot.pause()
            app.selected = ("plan", self.plan.id)
            app.action_plan_diff()
            await pilot.pause()
            self.assertIsInstance(app.screen, PlanDiffScreen)
            body = str(app.screen.query_one("#plan-diff-body").content)
            self.assertIn("TASKS", body)
            self.assertIn("Renamed task", body)
            await pilot.press("escape")
            await pilot.pause()
            app.selected = ("task", self.task.id)
            app.action_plan_diff()
            await pilot.pause()
            self.assertIsInstance(app.screen, PlanDiffScreen)
            await pilot.press("escape")

    async def test_clean_plan_action_paints_in_sync(self) -> None:
        services.approve(self.store, self.plan.id, actor="test", reason="start")
        app = create_app(str(self.store.path))
        async with app.run_test(size=(130, 35)) as pilot:
            await pilot.pause()
            app.selected = ("plan", self.plan.id)
            app.action_plan_diff()
            await pilot.pause()
            body = str(app.screen.query_one("#plan-diff-body").content)
            self.assertIn("in sync with the approved revision", body)


if __name__ == "__main__":
    unittest.main()
