"""The maintenance screen lists candidates, applies with confirm, and restores."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.shared import registry
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.forms import ConfirmScreen, FilterPromptScreen
    from lazyplan.presentation.tui.screens.maintenance import MaintenanceScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = ConfirmScreen = FilterPromptScreen = MaintenanceScreen = None  # type: ignore[assignment]


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestMaintenanceScreen(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "maint-tui.db"))
        self.plan = self.store.add_plan("Live plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Slice")
        self.task = self.store.add_task(self.milestone.id, "Task")
        self.old = time.time() - 10 * 86400
        self.old_plan = self.store.add_plan("Old plan")
        services.set_status(self.store, "plan", self.old_plan.id, Status.DONE)
        session, _previous = self.store.start_session(
            "builder", plan_id=self.old_plan.id, repo_path=self.tmp.name, now=self.old
        )
        self.store.end_session(session.id, "builder", summary="done", now=self.old)
        self.store.claim_task(
            self.task.id, "builder", ttl_seconds=60, now=self.old, repo_path=self.tmp.name
        )
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?, 'x', 'x', 'x', 'old')",
                (self.old,),
            )
            conn.execute("UPDATE events SET ts=? WHERE detail LIKE 'plan #% -> done%'", (self.old,))
            conn.commit()

    @property
    def db(self) -> str:
        return self.store.path

    def _entries(self) -> list:
        return MaintenanceScreen(self.store).load_entries()

    def test_screen_lists_every_trim_target_with_a_count(self) -> None:
        labels = [entry.label for entry in self._entries()]
        self.assertTrue(any(label.startswith("report") for label in labels))
        self.assertTrue(any(label.startswith("archive") for label in labels))
        self.assertTrue(any(label.startswith("trim  task_claims") for label in labels))
        self.assertTrue(any(label.startswith("vacuum") for label in labels))
        self.assertTrue(any(label.startswith("restore") for label in labels))
        self.assertIn("maintenance", registry.HUB_ACTIONS)

    async def test_pilot_applies_archive_and_restores(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            screen = MaintenanceScreen(self.store)
            app.push_screen(screen)
            await pilot.pause()
            self.assertIs(app.screen, screen)

            screen.action_apply_archive()
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            await pilot.click("#ok")
            await pilot.pause()
            archived = self.store.get_plan(self.old_plan.id)
            assert archived is not None
            self.assertGreater(archived.archived_at, 0)

            screen.action_restore()
            await pilot.pause()
            self.assertIsInstance(app.screen, FilterPromptScreen)
            await pilot.press("P", str(self.old_plan.id), "enter")
            await pilot.pause()
            restored = self.store.get_plan(self.old_plan.id)
            assert restored is not None
            self.assertEqual(restored.archived_at, 0.0)


if __name__ == "__main__":
    unittest.main()
