"""Selection context helpers shared by actions and the palette."""

from __future__ import annotations

from textual.widgets import Tree

from ..palette import COMMANDS
from .base import AppBase


class ContextMixin(AppBase):
    """Resolve the selected plan, milestone, task, and command context."""

    def _plan_ctx(self) -> int | None:
        if self.selected is None:
            return None
        kind, oid = self.selected
        if kind == "plan":
            return oid
        if kind == "milestone":
            milestone = self.store.get_milestone(oid)
            return milestone.plan_id if milestone else None
        if kind == "task":
            task = self.store.get_task(oid)
            if task is None:
                return None
            milestone = self.store.get_milestone(task.milestone_id)
            return milestone.plan_id if milestone else None
        return None

    def _milestone_for_task_ctx(self) -> int | None:
        if self.selected is None:
            return None
        kind, oid = self.selected
        if kind == "milestone":
            return oid
        if kind == "task":
            task = self.store.get_task(oid)
            return task.milestone_id if task else None
        return None

    def _selected_task(self) -> int | None:
        """Selected task id, or a notification when the selection is not a task."""
        if self.selected is None or self.selected[0] != "task":
            self.notify("select a task first", timeout=3)
            return None
        return self.selected[1]

    def _cursor_is_root(self) -> bool:
        """True when the cursor sits on the dataless plans root or empty tree."""
        try:
            tree = self.query_one("#tree", Tree)
        except Exception:
            return True
        try:
            cursor = tree.cursor_node
        except Exception:
            return True
        if cursor is None:
            return True
        return self._node_key(cursor) is None

    def _palette_context(self) -> dict[str, str | None]:
        """Disable commands that cannot run for the current selection."""
        selected = self.selected is not None
        plan_id = self._plan_ctx()
        milestone_id = self._milestone_for_task_ctx()
        context: dict[str, str | None] = {cmd.id: None for cmd in COMMANDS}
        if not selected:
            for cmd in COMMANDS:
                if cmd.context == "selection":
                    context[cmd.id] = "Select a row first"
        if plan_id is None:
            context["create-milestone"] = "Select a plan first"
            context["export-plan"] = "Select a plan first"
        if milestone_id is None:
            context["create-task"] = "Select a milestone first"
        if self.selected is not None and self.selected[0] == "task":
            context["fold-one"] = "Nothing to fold"
        return context
