"""Cross-plan proof: stable expansion, title-only task rows, live agents pane.

One mounted app is driven through structural writes, claim and block edits, and
session heartbeats. The plan branch must stay where the reader left it, task
rows must read as glyph + id + title + attention, and the agents card must stay
a compact live process list. Each rule already has its own suite; this one
proves they hold at the same time.
"""

from __future__ import annotations

import unittest

from lazyplan import services
from lazyplan.core.entities import Status

try:
    from rich.text import Text
    from textual.widgets import Static, Tree

    from lazyplan.presentation.tui import create_app
    from tests.presentation.test_refresh import RefreshCase
except ImportError:  # pragma: no cover - textual not installed
    create_app = None  # type: ignore[assignment]
    RefreshCase = unittest.TestCase  # type: ignore[misc,assignment]

HOST_SESSION = "ses_01JABCDEF4Z"


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestCombinedSurfaces(RefreshCase):
    """Expansion, task rows, and the agents card in one live screen."""

    def plain_row(self, app: object, key: tuple[str, int]) -> str:
        """The visible text of one tree row, without Rich markup."""
        return Text.from_markup(app._row_labels[key]).plain  # type: ignore[attr-defined]

    def branch_state(self, app: object) -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
        """The expansion sets the reader owns."""
        return set(app._expanded), set(app._collapsed)  # type: ignore[attr-defined]

    def agents_body(self, app: object) -> str:
        """The agents card's visible text, without Rich markup."""
        body = app.query_one("#agents-body", Static)  # type: ignore[attr-defined]
        return Text.from_markup(str(body.content)).plain

    def assert_task_row(self, app: object, task: object, state: str = "") -> None:
        """A task row is its id, its title, and at most one state word."""
        text = self.plain_row(app, ("task", task.id)).strip()  # type: ignore[attr-defined]
        tokens = text.split()
        self.assertEqual(tokens[0], f"T{task.id}")
        words = tokens[1:]
        if state:
            self.assertEqual(words[-1], state)
            words = words[:-1]
        self.assertEqual(" ".join(words), task.title)
        for banned in ("○", "◐", "●", "@", "◉", "⚑", "!", "0/"):
            self.assertNotIn(banned, text)

    async def test_writes_keep_the_tree_task_rows_and_agents_in_step(self) -> None:
        other = self.store.add_plan("Other", goal="keeps the queue busy")
        second = self.store.add_task(self.milestone.id, "Second task")
        blocked = self.store.add_task(self.milestone.id, "Blocked task")
        session = self.store.add_agent(
            "ana",
            agent="ana",
            plan_id=self.plan.id,
            branch="feat/integration",
            host="opencode",
            host_session=HOST_SESSION,
            worktree=self.store.checkout_path(),
            status="working",
        )
        self.store.claim_task(blocked.id, "lin", ttl_seconds=900, note="review")
        services.set_status(self.store, "task", blocked.id, Status.DOING, actor="ana")
        services.block_task(self.store, blocked.id, reason="waiting on review", actor="lin")

        app = create_app(self.store.path)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            harness = self.harness(app, session.id)
            self.expand_all(app)
            await pilot.pause()

            plan_key = ("plan", self.plan.id)
            milestone_key = ("milestone", self.milestone.id)
            plan_node = app._row_nodes[plan_key]
            expansion = self.branch_state(app)

            # Heartbeats repaint the card and never rebuild the tree.
            harness.heartbeat("working")
            await pilot.pause()
            body = self.agents_body(app)
            self.assertIn("@ana", body)
            self.assertIn(f"P{self.plan.id} {self.plan.name}", body)
            self.assertIn("feat/integration", body)
            self.assertNotRegex(body, r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]")
            self.assertIn("working", body)

            # Structural, claim, and block writes leave branches alone.
            added = self.store.add_task(self.milestone.id, "Third task", actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.store.claim_task(added.id, "sam", ttl_seconds=900, note="take it")
            app.refresh_all()
            await pilot.pause()
            services.cycle_status(self.store, "task", second.id, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.store.update_task(self.task.id, title="Renamed task", actor="ana")
            app.refresh_all()
            await pilot.pause()

            self.assertEqual(self.branch_state(app), expansion)
            self.assertIs(app._row_nodes[plan_key], plan_node)
            self.assertIs(plan_node.tree, app.query_one("#tree", Tree))
            self.assertTrue(app._row_nodes[milestone_key].is_expanded)
            self.assertTrue(app.tree_controller.is_visible(app._row_nodes[("task", added.id)]))

            # Every visible task row keeps the milestone shape.
            for task, state in (
                (self.task, ""),
                (second, "doing"),
                (blocked, "blocked"),
                (added, ""),
            ):
                self.assert_task_row(app, self.store.get_task(task.id), state=state)
            self.assertTrue(app._row_nodes[plan_key].is_expanded)

            # A settled session swaps the active glyph for the awaiting glyph.
            harness.heartbeat("waiting")
            await pilot.pause()
            body = self.agents_body(app)
            self.assertIn("◆", body)
            self.assertIn("waiting", body)

            # The owning plan never leaves its panel while tasks come and go.
            services.set_status(self.store, "task", added.id, Status.DONE, actor="ana")
            app.refresh_all()
            await pilot.pause()
            self.assertIs(plan_node.tree, app.query_one("#tree", Tree))
            self.assertIsNot(plan_node.tree, app.query_one("#tree-finished", Tree))
            self.assertEqual(self.branch_state(app), expansion)
            other_key = ("plan", other.id)
            self.assertIn(other_key, app._row_nodes)
            self.assertIs(app._row_nodes[other_key].tree, app.query_one("#tree", Tree))


if __name__ == "__main__":
    unittest.main()
