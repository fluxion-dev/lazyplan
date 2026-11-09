"""Textual app: actions."""

from __future__ import annotations

from pathlib import Path

try:
    from textual.widgets import Tree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from lazyplan.infrastructure.templates import load_template

from ... import services
from ..shared.export import display_path
from ..shared.palette import by_id
from .approval_actions import ApprovalMixin
from .claim_actions import ClaimMixin
from .evidence_actions import EvidenceMixin
from .finish_actions import FinishMixin
from .git_actions import GitActionMixin
from .history_actions import HistoryMixin
from .hub_actions import HubMixin
from .palette_handlers import palette_handlers
from .question_actions import QuestionMixin
from .reference_actions import ReferenceMixin
from .screens import (
    ConfirmScreen,
    ExportScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
)
from .status_actions import StatusMixin
from .theme import next_theme

if _TEXTUAL_OK:

    class ActionMixin(
        HistoryMixin,
        HubMixin,
        ApprovalMixin,
        ClaimMixin,
        EvidenceMixin,
        FinishMixin,
        QuestionMixin,
        ReferenceMixin,
        StatusMixin,
        GitActionMixin,
    ):
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
                self._saved("milestone created")

            self.push_screen(
                NewMilestoneScreen(
                    pid,
                    defaults=load_template("milestone", self.store.path).defaults,
                    context=f"P{pid}",
                ),
                cb,
            )

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
                if not services.delete_row(
                    self.store, kind, oid, actor="tui", reason=reason.strip()
                ):
                    self.notify("already gone — refreshing")
                    return
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

        def action_toggle_timeline(self) -> None:
            """Show or hide the timeline card for this session."""
            self.state.timeline_visible = not self.state.timeline_visible
            self._apply_layout()
            self.metrics_controller.refresh()

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

        def select_row(self, kind: str, oid: int) -> None:
            """Return to the tree and select one row in the overview."""
            while len(self.screen_stack) > 1:
                self.pop_screen()
            self.selected = (kind, oid)
            node = self._row_nodes.get((kind, oid))
            if node is not None:
                try:
                    tree = self.query_one("#tree", Tree)
                    tree.move_cursor(node)
                    tree.scroll_to_node(node)
                except Exception:
                    pass
            self.update_preview(force=True)

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
                    return
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
                    services.create_task(
                        self.store,
                        sid,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                    return
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

        def action_edit_selection(self) -> None:
            """Edit the selected row in a modal form."""
            if self.selected is None:
                self.notify("select a row first (e edits it)")
                return
            kind, oid = self.selected
            full = self.store.get_full(kind, oid)
            if full is None:
                self.notify("row is gone — refreshing")
                self._saved("row is gone")
                return
            screen: NewPlanScreen | NewMilestoneScreen | NewTaskScreen
            if kind == "plan":
                obj = full.get("plan", {})
                screen = NewPlanScreen(
                    defaults={
                        "title": str(obj.get("name", "")),
                        "why": str(obj.get("goal", "")),
                        "what": str(obj.get("description", "")),
                    },
                    editing=True,
                )
            elif kind == "milestone":
                obj = full.get("milestone", {})
                plan_id = int(obj.get("plan_id", 0))
                screen = NewMilestoneScreen(
                    plan_id,
                    defaults={
                        "title": str(obj.get("title", "")),
                        "desc": str(obj.get("description", "")),
                    },
                    context=f"P{plan_id}",
                    editing=True,
                )
            else:
                obj = full.get("task", {})
                milestone_id = int(obj.get("milestone_id", 0))
                screen = NewTaskScreen(
                    milestone_id,
                    defaults={
                        "title": str(obj.get("title", "")),
                        "desc": str(obj.get("description", "")),
                    },
                    context=f"M{milestone_id}",
                    editing=True,
                )

            def cb(data: dict | None) -> None:
                if data:
                    self._apply_edit(kind, oid, data)

            self.push_screen(screen, cb)

        def _apply_edit(self, kind: str, oid: int, data: dict) -> None:
            """Persist one edited row; the overview refreshes on success."""
            title = str(data.get("title", "")).strip()
            if not title:
                self.notify("title must not be empty")
                return
            try:
                if kind == "plan":
                    self.store.update_plan(
                        oid,
                        name=title,
                        description=str(data.get("what", "")),
                        goal=str(data.get("why", "")) or None,
                        actor="tui",
                    )
                elif kind == "milestone":
                    self.store.update_milestone(
                        oid,
                        title=title,
                        description=str(data.get("desc", "")),
                        actor="tui",
                    )
                else:
                    self.store.update_task(
                        oid,
                        title=title,
                        description=str(data.get("desc", "")),
                        actor="tui",
                    )
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}")
                return
            self._saved(f"saved {kind}")

        async def action_quit(self) -> None:
            """Leave the screen (q)."""
            self.exit()
