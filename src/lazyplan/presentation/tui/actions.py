"""Textual app: actions."""

from __future__ import annotations

import time
from pathlib import Path

try:
    from textual.widgets import Tree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from lazyplan.infrastructure.templates import load_template

from ... import services
from ...core.entities import Status
from ..shared.export import display_path
from ..shared.palette import by_id
from .claim_actions import ClaimMixin
from .constants import DOUBLE_CLICK_WINDOW
from .git_actions import GitActionMixin
from .override import WRITE_COMMANDS, OverrideMixin
from .palette_handlers import palette_handlers
from .screens import (
    ConfirmScreen,
    DetailScreen,
    ExportScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
)

if _TEXTUAL_OK:

    class ActionMixin(OverrideMixin, ClaimMixin, GitActionMixin):
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
                    return
                self._record_override("milestone add", f"P{pid}")
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
            self._record_override(
                "criterion reopen" if reopen else "criterion tick", f"C{target.id}"
            )
            self._saved(f"criterion {target.id} {verb}")

        def action_delete(self) -> None:
            if self.selected is None:
                self.notify("select a row first (d deletes with confirm)")
                return
            kind, oid = self.selected

            def reason_cb(reason: str | None) -> None:
                if reason is None:
                    return
                if not reason.strip():
                    self.notify("a delete needs a reason", timeout=3)
                    return
                if not self.store.delete(kind, oid, actor="tui"):
                    self.notify("already gone — refreshing")
                    return
                self._record_override("delete", f"{kind} #{oid}", reason.strip())
                self.selected = None
                self._saved(f"deleted {kind} #{oid}")

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                self.push_screen(
                    FilterPromptScreen(
                        title=f"Delete {kind} #{oid}? Why?",
                        placeholder="reason for deleting…",
                        submit_label="Delete",
                    ),
                    reason_cb,
                )

            self.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)

        def action_export_md(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a row first, then export")
                return
            plan = self.store.get_plan(pid)
            if plan is None:
                self.notify("selected plan no longer exists — refreshing")
                self.refresh_all("")
                return

            def cb(path: Path | None) -> None:
                if path is not None:
                    self.notify(f"exported {display_path(path)}", timeout=4)

            self.push_screen(ExportScreen(self.store, pid, plan.name), cb)

        def action_refresh(self) -> None:
            self._saved("manual refresh")

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
                self._record_override("criterion add", f"{kind} #{oid}")
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
            else:
                self._record_override("status", f"{kind} #{oid}", nxt.value)
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
                    plan = services.create_plan(
                        self.store,
                        data["title"],
                        data["what"],
                        goal=data["why"],
                        actor="tui",
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                    return
                self._record_override("plan add", f"P{plan.id}")
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
            if command.handler in WRITE_COMMANDS and not self.override_mode:
                self.notify("read-only — press O for manual override", timeout=3)
                return
            handlers = palette_handlers(self)
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
                    task = services.create_task(
                        self.store,
                        sid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                    return
                self._record_override("task add", f"T{task.id}")
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
            self._record_override("criterion reopen", f"C{target.id}")
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
            self._record_override("status", f"{kind} #{oid}", status.value)
            self._saved(f"{kind} {oid} -> {status.value}")

        async def action_quit(self) -> None:
            """Leave the screen (q)."""
            self.exit()
