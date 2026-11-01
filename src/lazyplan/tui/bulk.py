"""Textual app: bulk."""

from __future__ import annotations

try:
    from .base import AppBase

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from ..models import Status, Task
from ..store import ClaimConflict
from .screens import (
    ConfirmScreen,
    FilterPromptScreen,
)

if _TEXTUAL_OK:

    class BulkMixin(AppBase):
        """Bulk behavior."""

        def action_toggle_mark(self) -> None:
            if self.selected is None:
                self.notify("select a row first", timeout=3)
                return
            key = self.selected
            if key in self.marked:
                self.marked.remove(key)
            else:
                self.marked.add(key)
            self._paint_mark(key)

        def action_bulk_done(self) -> None:
            self._bulk_status(Status.DONE)

        def _bulk_capture(self, tasks: list[Task]) -> None:
            """Remember exact state for one undo."""
            self._undo = [
                {
                    "id": task.id,
                    "status": task.status,
                    "blocked": task.blocked,
                    "reason": task.blocked_reason,
                }
                for task in tasks
            ]

        def action_bulk_doing(self) -> None:
            self._bulk_status(Status.DOING)

        def _marked_tasks(self) -> list[Task]:
            """Task rows in the mark set."""
            return [
                task
                for kind, oid in self.marked
                if kind == "task" and (task := self.store.get_task(oid)) is not None
            ]

        def action_bulk_release(self) -> None:
            tasks = self._marked_tasks()
            if not tasks:
                self.notify("mark at least one task first", timeout=3)
                return

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                released = 0
                conflicts = 0
                for task in tasks:
                    try:
                        if self.store.release_claim(task.id, "tui") is not None:
                            released += 1
                    except ClaimConflict:
                        conflicts += 1
                self.marked.clear()
                self._saved(f"released {released}, conflicts {conflicts}")

            self.push_screen(ConfirmScreen(f"Release claims on {len(tasks)} marked tasks?"), cb)

        def action_undo_bulk(self) -> None:
            if not self._undo:
                self.notify("nothing to undo", timeout=3)
                return
            states = self._undo
            for state in states:
                services.set_status(self.store, "task", state["id"], state["status"], actor="tui")
                self.store.set_blocked(state["id"], state["blocked"], state["reason"], actor="tui")
            self._undo = None
            self._saved(f"undid {len(states)} task changes")

        def _bulk_status(self, status: Status) -> None:
            tasks = self._marked_tasks()
            if not tasks:
                self.notify("mark at least one task first", timeout=3)
                return

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                self._bulk_capture(tasks)
                for task in tasks:
                    services.set_status(self.store, "task", task.id, status, actor="tui")
                self.marked.clear()
                self._saved(f"moved {len(tasks)} tasks to {status.value}")

            self.push_screen(
                ConfirmScreen(f"Move {len(tasks)} marked tasks to {status.value}?"), cb
            )

        def action_clear_marks(self) -> None:
            for key in list(self.marked):
                self.marked.discard(key)
                self._paint_mark(key)

        def action_bulk_block(self) -> None:
            tasks = self._marked_tasks()
            if not tasks:
                self.notify("mark at least one task first", timeout=3)
                return

            def reason_cb(reason: str | None) -> None:
                if reason is None or not reason.strip():
                    return

                def cb(confirmed: bool | None) -> None:
                    if not confirmed:
                        return
                    self._bulk_capture(tasks)
                    for task in tasks:
                        services.block_task(self.store, task.id, reason.strip(), actor="tui")
                    self.marked.clear()
                    self._saved(f"blocked {len(tasks)} tasks")

                self.push_screen(ConfirmScreen(f"Block {len(tasks)} tasks: {reason.strip()}?"), cb)

            self.push_screen(FilterPromptScreen(), reason_cb)
