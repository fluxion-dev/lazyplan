"""Progress card rendering: headline, milestone bars, and empty states."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan import metrics, services
from lazyplan.models import Status
from lazyplan.store import Store

try:
    from lazyplan import tui as tui_mod
    from lazyplan.tui.metrics.progress import ProgressCard, render_progress
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]
    ProgressCard = None  # type: ignore[assignment,misc]
    render_progress = None  # type: ignore[assignment]


def _progress(store: Store) -> metrics.OverallProgress:
    result = metrics.snapshot(store).progress
    assert result is not None
    return result


def _seed(store: Store) -> None:
    plan = store.add_plan("Plan")
    first = store.add_milestone(plan.id, "First milestone")
    second = store.add_milestone(plan.id, "Second milestone")
    done = store.add_task(first.id, "Done task")
    store.add_task(first.id, "Open task")
    store.add_task(second.id, "Other task")
    services.set_status(store, "task", done.id, Status.DONE, actor="qa")


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ProgressCardRenderTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.store = Store(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_card_renders_headline_and_milestones(self) -> None:
        _seed(self.store)
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress", ProgressCard)
            card.refresh_progress(_progress(self.store))
            await pilot.pause()
            body = str(card.query_one(".metric-body").render())
        self.assertIn("33% 1/3", body)
        self.assertIn("ETA", body)
        self.assertIn("1/2 First milestone", body)
        self.assertIn("0/1 Second milestone", body)

    async def test_card_uses_the_empty_state(self) -> None:
        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one("#metric-progress", ProgressCard)
            card.refresh_progress(_progress(self.store))
            body = str(card.query_one(".metric-body").render())
        self.assertIn("no plans yet", body)

    async def test_complete_headline_skips_the_eta(self) -> None:
        _seed(self.store)
        for tasks in self.store.tasks_map().values():
            for task in tasks:
                services.set_status(self.store, "task", task.id, Status.DONE, actor="qa")
        body = render_progress(_progress(self.store))
        self.assertIn("100% 3/3 · complete", body)
        self.assertNotIn("ETA", body)


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class ProgressBodyTest(unittest.TestCase):
    def test_elapsed_dash_when_no_events(self) -> None:
        body = render_progress(metrics.OverallProgress(done=1, total=2))
        self.assertIn("1/2", body)
        self.assertIn("—", body)

    def test_markup_in_a_milestone_title_is_escaped(self) -> None:
        item = metrics.MilestoneProgress(1, 1, "[bold]M", done=0, total=1)
        body = render_progress(metrics.OverallProgress(done=0, total=1, milestones=(item,)))
        self.assertIn("\\[bold]M", body)


if __name__ == "__main__":
    unittest.main()
