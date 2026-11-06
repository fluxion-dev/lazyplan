"""Focus lens: doing, claims, blocked, attention, and next work."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.shared.palette import by_id
from lazyplan.store import Store

try:
    from lazyplan.presentation.tui import filters as filters_mod
    from lazyplan.presentation.tui.controllers.filtering import TreeFilter

    _TUI_OK = True
except ImportError:  # stdlib-only interpreter: no textual
    filters_mod = None  # type: ignore[assignment]
    TreeFilter = None  # type: ignore[assignment,misc]
    _TUI_OK = False


@unittest.skipUnless(_TUI_OK, "textual required")
class FocusLensTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")
        self.plan = self.store.add_plan("P")
        self.milestone = self.store.add_milestone(self.plan.id, "M")
        self.doing = self.store.add_task(self.milestone.id, "Doing")
        self.claimed = self.store.add_task(self.milestone.id, "Claimed")
        self.blocked = self.store.add_task(self.milestone.id, "Blocked")
        self.next_task = self.store.add_task(self.milestone.id, "Next")
        self.later = self.store.add_task(self.milestone.id, "Later")
        self.done = self.store.add_task(self.milestone.id, "Done")
        services.set_status(self.store, "task", self.doing.id, Status.DOING, actor="t")
        self.store.claim_task(self.claimed.id, "alice", 300)
        self.store.set_blocked(self.blocked.id, True, "waiting", actor="t")
        services.set_status(self.store, "task", self.done.id, Status.DONE, actor="t")

    def tearDown(self):
        self.tmp.cleanup()

    def _focus(self):
        app = SimpleNamespace(store=self.store, source_filter="focus")
        tree_filter = TreeFilter(app)
        base = services.tree(self.store)
        return tree_filter.filter_source_tree(base, tree_filter.source_stats(base))

    def test_focus_keeps_the_active_slice(self):
        kept = {
            task.id
            for _plan, milestones in self._focus()
            for _milestone, tasks in milestones
            for task in tasks
        }
        self.assertEqual(
            kept,
            {self.doing.id, self.claimed.id, self.blocked.id, self.next_task.id},
        )

    def test_focus_keeps_parent_context(self):
        filtered = self._focus()
        self.assertEqual(filtered[0][0].id, self.plan.id)
        self.assertEqual(filtered[0][1][0][0].id, self.milestone.id)

    def test_source_filter_cycle_includes_focus(self):
        assert filters_mod is not None
        self.assertIn("focus", filters_mod.FilterMixin.SOURCE_FILTERS)

    def test_palette_hint_names_focus(self):
        command = by_id("filter-source")
        assert command is not None
        self.assertIn("focus", command.help_hint)


if __name__ == "__main__":
    unittest.main()
