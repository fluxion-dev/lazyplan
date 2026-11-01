"""Textual app: actions."""

from __future__ import annotations

import time
from typing import Any

from .. import textfile

try:
    from textual.widgets import Tree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from ..models import Status
from ..palette import by_id
from ..store import ClaimConflict
from ..templates import load_template
from .constants import DOUBLE_CLICK_WINDOW
from .context import ContextMixin
from .git_actions import GitActionMixin
from .screens import (
    ConfirmScreen,
    DetailScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
)
from .theme import next_theme

if _TEXTUAL_OK:

    class ActionMixin(ContextMixin, GitActionMixin):
        """Actions behavior."""

        def action_new_milestone(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a plan first (j/k + click)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_milestone(
                        self.store,
                        pid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("milestone created")

            self.push_screen(
                NewMilestoneScreen(
                    pid,
                    defaults=load_template("milestone", self.store.path).defaults,
                    context=f"P{pid}",
                ),
                cb,
            )

        def _open_detail(self, kind: str, oid: int, edit: bool = False) -> None:
            def cb(saved: bool | None) -> None:
                if saved:
                    self._saved("saved detail")

            self.push_screen(DetailScreen(self.store, kind, oid, edit=edit), cb)

        def action_criteria(self) -> None:
            """Tick first open criterion; if none open, reopen the last done one."""
            if self.selected is None:
                self.notify("select a row first (x ticks criteria)")
                return
            kind, oid = self.selected
            items = self.store.list_criteria(kind, oid)
            if not items:
                self.notify(
                    f'no criteria — add via: lpui add-criteria --kind {kind} --id {oid} --text "..."'
                )
                return
            open_items = [c for c in items if not c.done]
            if open_items:
                target, reopen = open_items[0], False
            else:
                target, reopen = items[-1], True  # nothing open: re-affirm by reopening last
            self.store.set_criteria(target.id, not reopen, actor="tui")
            verb = "reopened" if reopen else "checked"
            self._saved(f"criterion {target.id} {verb}")

        def action_delete(self) -> None:
            if self.selected is None:
                self.notify("select a row first (d deletes with confirm)")
                return
            kind, oid = self.selected

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                if not self.store.delete(kind, oid, actor="tui"):
                    self.notify("already gone — refreshing")
                self.selected = None
                self._saved(f"deleted {kind} #{oid}")

            self.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)

        def action_export_md(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a row first, then export")
                return
            entry = services.export_plan(self.store, pid)
            if entry is None:
                self.notify("selected plan no longer exists — refreshing")
                self.refresh_all("")
                return
            from ..render import render_plan_markdown  # noqa: F401

            path = f"plan-P{pid}.md"
            textfile.write(path, render_plan_markdown(entry) + "\n")
            self._saved(f"exported {path}")

        def action_force_release_claim(self) -> None:
            self._release_claim(True)

        def action_refresh(self) -> None:
            self._saved("manual refresh")

        def action_cycle_theme(self) -> None:
            """Cycle mocha, void, and latte; the chart redraws after the CSS."""
            selected = next_theme(self.theme)
            self.theme = selected
            self.notify(f"theme: {selected.removeprefix('lazyplan-')}", timeout=2)
            self.call_after_refresh(self.metrics_controller.refresh)

        def action_command_palette(self) -> None:
            """Open the modal command palette (c)."""
            if len(self.screen_stack) > 1:
                return
            self.push_screen(PaletteScreen(self._palette_context()), self._run_palette_command)

        def action_new_context(self) -> None:
            if self._cursor_is_root():
                self.action_new_plan()
                return
            sid = self._milestone_for_task_ctx()
            if sid is not None:
                self.action_new_task()
                return
            pid = self._plan_ctx()
            if pid is not None:
                self.action_new_milestone()
                return
            self.action_new_plan()

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        def action_add_criterion(self) -> None:
            """Prompt for a new criterion on the selected row."""
            if self.selected is None:
                self.notify("select a row first (a adds a criterion)")
                return
            kind, oid = self.selected

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    self.store.add_criteria(kind, oid, text, actor="tui")
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                    return
                self._saved("criterion added")

            self.push_screen(
                FilterPromptScreen(
                    title=f"New criterion on {kind} {oid}",
                    placeholder="what must be true?",
                    submit_label="Add",
                ),
                cb,
            )

        def action_toggle_status(self) -> None:
            if self.selected is None:
                self.notify("select a row first (s advances status)")
                return
            kind, oid = self.selected
            left = self.store.open_criteria(kind, oid)
            current = self.store.get_parent(kind, oid)
            if left and (current is None or current.status != Status.DONE):
                # advisory only: warn, then proceed (flow first)
                self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            nxt = services.cycle_status(self.store, kind, oid, actor="tui")
            if nxt is None:
                self.notify("selected row no longer exists")
            self._saved(f"{kind} {oid} -> {nxt.value if nxt else '?'}")

        def action_open_detail(self) -> None:
            if len(self.screen_stack) > 1:
                return  # a modal owns enter
            if self.selected is None:
                self.notify("select a row first, then enter")
                return
            self._open_detail(*self.selected)

        def _saved(self, note: str = "") -> None:
            """Local mutation path: bump reactive rev, watch refreshes."""
            self._pending_note = note
            try:
                self.rev += 1
            except Exception:
                self._fp = self.store.fingerprint()
                self.refresh_all(note)

        def action_new_plan(self) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_plan(
                        self.store,
                        data["title"],
                        data["what"],
                        goal=data["why"],
                        actor="tui",
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._saved("plan created")

            self.push_screen(
                NewPlanScreen(defaults=load_template("plan", self.store.path).defaults), cb
            )

        def _run_palette_command(self, command_id: str | None) -> None:
            """Run one palette command id through the shared registry."""
            if not command_id:
                return
            command = by_id(command_id)
            if command is None:
                return
            handlers: dict[str, Any] = {
                "new_plan": self.action_new_plan,
                "new_milestone": self.action_new_milestone,
                "new_task": self.action_new_task,
                "add_criterion": self.action_add_criterion,
                "edit_selection": self.action_edit_selection,
                "move_todo": lambda: self.action_move(Status.TODO),
                "move_doing": lambda: self.action_move(Status.DOING),
                "move_done": lambda: self.action_move(Status.DONE),
                "tick_criterion": self.action_criteria,
                "untick_criterion": self.action_untick_criterion,
                "delete_selection": self.action_delete,
                "open_detail": self.action_open_detail,
                "fold": self.action_fold,
                "fold_all": self.action_fold_all,
                "filter_text": self.action_filter_text,
                "filter_status": self.action_filter_status,
                "filter_source": self.action_filter_source,
                "toggle_show_all": self.action_toggle_show_all,
                "refresh": self.action_refresh,
                "git_status": self.action_git_status,
                "git_refresh": self.action_git_refresh,
                "git_capture": self.action_git_capture,
                "toggle_mark": self.action_toggle_mark,
                "clear_marks": self.action_clear_marks,
                "bulk_doing": self.action_bulk_doing,
                "bulk_done": self.action_bulk_done,
                "bulk_block": self.action_bulk_block,
                "bulk_release": self.action_bulk_release,
                "undo_bulk": self.action_undo_bulk,
                "release_claim": self.action_release_claim,
                "force_release_claim": self.action_force_release_claim,
                "open_pr": self.action_open_pr,
                "source_trail": self.action_source_trail,
                "command_palette": self.action_command_palette,
                "cycle_theme": self.action_cycle_theme,
                "export_md": self.action_export_md,
                "help": self.action_help,
                "update_prompt": self.action_update_prompt,
                "quit": self.exit,
            }
            fn = handlers.get(command.handler)
            if fn is None:
                return
            fn()
            self._pending_note = command.label.lower()

        def action_new_task(self) -> None:
            sid = self._milestone_for_task_ctx()
            if sid is None:
                self.notify("select a milestone first (n on a plan creates one)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_task(
                        self.store,
                        sid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("task created")

            milestone = self.store.get_milestone(sid)
            where = f"P{milestone.plan_id} › M{sid}" if milestone else f"M{sid}"
            self.push_screen(
                NewTaskScreen(
                    sid,
                    defaults=load_template("task", self.store.path).defaults,
                    context=where,
                ),
                cb,
            )

        def action_release_claim(self) -> None:
            self._release_claim(False)

        def action_untick_criterion(self) -> None:
            """Reopen the last ticked criterion on the selected row."""
            if self.selected is None:
                self.notify("select a row first (x ticks criteria)")
                return
            kind, oid = self.selected
            done = [c for c in self.store.list_criteria(kind, oid) if c.done]
            if not done:
                self.notify("no ticked criteria to reopen")
                return
            target = done[-1]
            self.store.set_criteria(target.id, False, actor="tui")
            self._saved(f"criterion #{target.id} reopened")

        def action_edit_selection(self) -> None:
            """Edit the selected row; detail owns the edit form."""
            if self.selected is None:
                self.notify("select a row first (e edits it)")
                return
            self._open_detail(*self.selected, edit=True)

        def note_click(self, key: tuple[str, int]) -> bool:
            """True when this click completes a double-click on the same row."""
            now = time.monotonic()
            double = (
                key == self._last_click_key and (now - self._last_click_at) < DOUBLE_CLICK_WINDOW
            )
            self._last_click_key, self._last_click_at = key, now
            return double

        def action_move(self, status: Status) -> None:
            """Move the selection to an explicit status (palette)."""
            if self.selected is None:
                self.notify("select a row first, then move it")
                return
            kind, oid = self.selected
            left = self.store.open_criteria(kind, oid)
            if status == Status.DONE and left:
                self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            if not services.set_status(self.store, kind, oid, status, actor="tui"):
                self.notify("selected row no longer exists")
                return
            self._saved(f"{kind} {oid} -> {status.value}")

        def _release_claim(self, force: bool) -> None:
            task_id = self._selected_task()
            if task_id is None:
                return
            try:
                claim = self.store.release_claim(task_id, "tui", force=force)
            except ClaimConflict as exc:
                self.notify(str(exc), severity="error", timeout=5)
                return
            if claim is None:
                self.notify(f"T{task_id} has no claim", timeout=3)
                return
            self.notify(f"released T{task_id} from {claim.actor}", timeout=3)
            self.refresh_all("claim released")

        async def action_quit(self) -> None:
            """Leave the screen (q)."""
            self.exit()
