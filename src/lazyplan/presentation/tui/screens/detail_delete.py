"""Destructive detail action: confirm, require a reason, then delete."""

from __future__ import annotations

from typing import Any

from lazyplan import services

from .forms import ConfirmScreen, FilterPromptScreen


def confirm_delete(screen: Any) -> None:
    """Ask for confirmation and a reason before deleting the detail row."""
    title = str(screen._obj().get("title", screen._obj().get("name", "")))
    lines = [f'Delete {screen.dkind} {screen.doid} "{title}"?']
    criteria = len(screen._dstore.list_criteria(screen.dkind, screen.doid))
    if screen.dkind == "plan":
        milestones = screen._dstore.list_milestones(screen.doid)
        tasks = sum(len(screen._dstore.list_tasks(item.id)) for item in milestones)
        lines.append(
            f"Also deletes {len(milestones)} milestones, {tasks} tasks, {criteria} criteria."
        )
    elif screen.dkind == "milestone":
        tasks = len(screen._dstore.list_tasks(screen.doid))
        lines.append(f"Also deletes {tasks} tasks and {criteria} criteria.")
    elif criteria:
        lines.append(f"Also deletes {criteria} criteria.")

    def reason_cb(reason: str | None) -> None:
        if reason is None:
            return
        if not reason.strip():
            screen.notify("a delete needs a reason", timeout=3)
            return
        if not services.delete_row(
            screen._dstore, screen.dkind, screen.doid, actor="tui", reason=reason.strip()
        ):
            screen.notify("row is already gone", timeout=3)
            return
        screen.dismiss(True)

    def cb(confirmed: bool | None) -> None:
        if not confirmed:
            return
        screen.app.push_screen(
            FilterPromptScreen(
                title=f"Delete {screen.dkind} {screen.doid}? Why?",
                placeholder="reason for deleting…",
                submit_label="Delete",
            ),
            reason_cb,
        )

    screen.app.push_screen(ConfirmScreen("\n".join(lines)), cb)
