"""External-change polling: heartbeats, structural edits, and rebuild counts."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import create_app
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]


class PollHarness:
    """One open session plus a hand-driven external-change poll.

    The app's own one-second timer is never waited on: tests call `poll()`
    after each database write so a heartbeat or edit is observed at a known
    point in time.
    """

    def __init__(self, app: object, store: Store, session_id: int) -> None:
        self.app = app
        self.store = store
        self.session_id = session_id

    def poll(self) -> None:
        """Run exactly one external-change poll."""
        self.app.tree_controller.poll()  # type: ignore[attr-defined]

    def heartbeat(self, phase: str = "working") -> None:
        """Touch the open session, then poll once."""
        self.store.touch_session(self.session_id, phase=phase)
        self.poll()

    @property
    def rebuilds(self) -> int:
        """How many full tree rebuilds the controller has run."""
        return int(self.app.tree_controller.rebuilds)  # type: ignore[attr-defined]


@unittest.skipUnless(create_app is not None, "textual not installed")
class RefreshCase(unittest.IsolatedAsyncioTestCase):
    """A mounted app with one plan, milestone, and task."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(os.path.join(self.tmp.name, "refresh.db"))
        self.plan = self.store.add_plan("Plan")
        self.milestone = self.store.add_milestone(self.plan.id, "Milestone")
        self.task = self.store.add_task(self.milestone.id, "Task")

    def harness(self, app: object) -> PollHarness:
        session, _ = self.store.start_session("ana", plan_id=self.plan.id)
        return PollHarness(app, self.store, session.id)


class TestHeartbeatRebuilds(RefreshCase):
    async def test_a_touched_heartbeat_rebuilds_the_tree(self) -> None:
        app = create_app(self.store.path)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            harness = self.harness(app)
            before = harness.rebuilds
            harness.heartbeat()
            self.assertEqual(harness.rebuilds - before, 1)


if __name__ == "__main__":
    unittest.main()
