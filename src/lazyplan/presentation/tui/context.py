"""Selection context helpers shared by actions and the palette."""

from __future__ import annotations

from collections.abc import Callable

from textual.widgets import Tree

from ..shared import registry
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
        """True when neither plan panel holds a real row under its cursor."""
        for tree_id in ("#tree", "#tree-finished"):
            try:
                tree = self.query_one(tree_id, Tree)
                cursor = tree.cursor_node
            except Exception:
                continue
            if cursor is not None and self._node_key(cursor) is not None:
                return False
        return True

    def _palette_context(self) -> dict[str, str | None]:
        """Disable commands the current screen and selection cannot run.

        The rules live in the registry; this method only reports the context.
        """
        context = registry.Context(
            screen=self._screen_name(),
            selected_kind=self.selected[0] if self.selected else None,
            has_plan=self._plan_ctx() is not None,
            has_milestone=self._milestone_for_task_ctx() is not None,
            on_root=self._cursor_is_root(),
        )
        return registry.palette_context(context)

    def _screen_name(self) -> str:
        """The navigation name of the top screen, or tree before mount."""
        try:
            screen = self.screen
        except Exception:
            return "tree"
        return str(getattr(screen, "navigation_name", "tree"))

    def prompt_reason(
        self,
        title: str,
        placeholder: str,
        submit: str,
        callback: Callable[[str], None],
        empty_message: str = "a reason is required",
    ) -> None:
        """Ask for a non-empty reason and hand it to one callback."""

        from .screens import FilterPromptScreen

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify(empty_message, timeout=3)
                return
            callback(reason.strip())

        self.push_screen(
            FilterPromptScreen(title=title, placeholder=placeholder, submit_label=submit),
            reason_cb,
        )
