"""Coordination hubs: claims and touch-points, sessions, comments and notes."""

from __future__ import annotations

import time

try:
    from textual.binding import Binding

    from .hub import HubEntry, HubScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from .... import services
from ....core.errors import ClaimError
from ...shared.design import escape_markup
from .forms import FilterPromptScreen


def _age(stamp: float, now: float) -> str:
    minutes = int(max(0.0, now - stamp) / 60)
    return f"{minutes}m" if minutes < 60 else f"{minutes // 60}h{minutes % 60:02d}m"


if _TEXTUAL_OK:

    class ClaimsHub(HubScreen):
        """Active and expired claims plus touch-points for one task or plan."""

        kind = "claims"
        primary_hint = ("a", "claim task")
        BINDINGS = [Binding("x", "hub_toggle", "Toggle")]

        def __init__(
            self, store: object, task_id: int | None = None, plan_id: int | None = None
        ) -> None:
            super().__init__(store)
            self.task_id = task_id
            self.plan_id = plan_id
            self.title = f"claims · T{task_id}" if task_id is not None else "claims"
            self.empty = "No claims or touch-points. Press a to claim a task."

        @property
        def source_parent(self) -> tuple[str, int] | None:
            if self.task_id is not None:
                return ("task", self.task_id)
            if self.plan_id is not None:
                return ("plan", self.plan_id)
            return None

        def load_entries(self) -> list[HubEntry]:
            now = time.time()
            all_claims = services.coordination.list_claims(
                self.store, include_expired=True, plan_id=self.plan_id
            )
            claims = all_claims
            if self.task_id is not None:
                claims = [row for row in claims if int(row["task_id"]) == self.task_id]
            touch_map = self.store.touchpoints_map()
            out: list[HubEntry] = []
            for row in claims:
                task_id = int(row["task_id"])
                expired = bool(row.get("expired"))
                state = "expired" if expired else "active"
                overlaps = self._overlaps(task_id, all_claims, touch_map)
                body = (
                    f"T{task_id} · {state}\n"
                    f"holder   @{escape_markup(str(row['actor']))}\n"
                    f"expires  {time.strftime('%Y-%m-%d %H:%M', time.localtime(float(row['expires_at'])))}\n"
                    f"age      {_age(float(row['started_at']), now)}\n"
                    f"note     {escape_markup(str(row.get('note') or '—'))}"
                )
                if overlaps:
                    body += "\noverlap  " + ", ".join(f"T{item}" for item in overlaps)
                label = f"@{row['actor']} T{task_id} {state}"
                out.append(HubEntry(task_id, label, body, "claim"))
            if self.task_id is not None:
                for pattern in touch_map.get(self.task_id, ()):
                    body = f"touch-point on T{self.task_id}\n{escape_markup(pattern)}"
                    out.append(HubEntry(self.task_id, f"touch {pattern}", body, "touch", pattern))
            return out

        @staticmethod
        def _overlaps(
            task_id: int, claims: list[dict], touch_map: dict[int, list[str]]
        ) -> list[int]:
            mine = set(touch_map.get(task_id, ()))
            out: list[int] = []
            for row in claims:
                other = int(row["task_id"])
                if other == task_id or bool(row.get("expired")):
                    continue
                if mine & set(touch_map.get(other, ())):
                    out.append(other)
            return sorted(out)

        def _task_id(self) -> int | None:
            entry = self._selected()
            if entry is not None:
                return entry.oid
            return self.task_id

        def add(self) -> None:
            task_id = self._task_id()
            if task_id is None:
                self.notify("select a task first", timeout=3)
                return
            try:
                self.store.claim_task(task_id, "tui")
            except (ValueError, KeyError, ClaimError) as exc:
                self.notify(f"error: {exc}", timeout=4)
                return
            self._reload()

        def toggle(self) -> None:
            task_id = self._task_id()
            if task_id is None:
                return
            try:
                self.store.renew_claim(task_id, "tui")
            except (ValueError, KeyError, ClaimError) as exc:
                self.notify(f"error: {exc}", timeout=4)
                return
            self._reload()

        def delete_row(self) -> None:
            self._release(force=False)

        def force(self) -> None:
            self._release(force=True)

        def _release(self, force: bool) -> None:
            task_id = self._task_id()
            if task_id is None:
                return
            try:
                self.store.release_claim(task_id, "tui", force=force)
            except (ValueError, KeyError, ClaimError) as exc:
                self.notify(f"error: {exc}", timeout=4)
                return
            self._reload()

        def relate(self) -> None:
            task_id = self._task_id()
            if task_id is None:
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    self.store.add_touchpoint(task_id, text, actor="tui")
                except (ValueError, KeyError, ClaimError) as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Add touch-point", "repo-relative path or glob", "Add"), cb
            )

        def unrelate(self) -> None:
            entry = self._selected()
            task_id = self._task_id()
            pattern = entry.ref if entry is not None and entry.kind == "touch" else ""
            if task_id is None:
                return
            if pattern:
                self.store.remove_touchpoint(task_id, pattern, actor="tui")
                self._reload()
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                self.store.remove_touchpoint(task_id, text, actor="tui")
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Remove touch-point", "path or glob", "Remove"), cb
            )

    class SessionsHub(HubScreen):
        """Sessions and handoffs for one plan."""

        kind = "sessions"
        primary_hint = ("a", "start session")
        BINDINGS = [Binding("x", "hub_toggle", "Toggle")]

        def __init__(self, store: object, plan_id: int) -> None:
            super().__init__(store)
            self.plan_id = plan_id
            self.title = f"sessions · P{plan_id}"
            self.empty = "No sessions yet. Press a to start one."

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return ("plan", self.plan_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            stamp = time.time()
            for session in services.sessions.list_sessions(
                self.store, plan_id=self.plan_id, limit=50
            ):
                state = services.session_state(session, stamp)
                body = (
                    f"S{session.id} · {state}\n"
                    f"actor   @{escape_markup(session.actor)}\n"
                    f"host    {escape_markup(session.host or '—')}\n"
                    f"plan    P{session.plan_id}\n"
                    f"branch  {escape_markup(session.branch or '—')}\n"
                    f"age     {_age(session.started_at, stamp)}\n"
                    f"idle    {_age(session.last_activity(), stamp)}\n"
                    f"summary {escape_markup(session.summary or '—')}\n"
                    f"handoff {escape_markup(session.handoff or '—')}"
                )
                detail = services.sessions.show_session(self.store, session.id, limit=5)
                events = detail.get("events", []) if detail else []
                if events:
                    body += "\nevents  " + " · ".join(
                        f"{event.get('action', '')} {str(event.get('detail', ''))[:30]}"
                        for event in events
                    )
                out.append(HubEntry(session.id, f"S{session.id} @{session.actor} {state}", body))
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                try:
                    services.sessions.start_session(
                        self.store,
                        "tui",
                        plan_id=self.plan_id,
                        branch=(text or "").strip(),
                    )
                except (ValueError, KeyError, ClaimError) as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Start session", "branch (optional)", "Start"), cb
            )

        def delete_row(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return

            def cb(text: str | None) -> None:
                try:
                    services.sessions.end_session(
                        self.store, entry.oid, "tui", summary=(text or "").strip()
                    )
                except (ValueError, KeyError, ClaimError) as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(FilterPromptScreen("End session", "summary (optional)", "End"), cb)

        def toggle(self) -> None:
            self.delete_row()

    class CommentsHub(HubScreen):
        """Comments and notes on one row, with an unresolved filter."""

        kind = "comments"
        primary_hint = ("a", "add comment")
        BINDINGS = [
            Binding("e", "edit_row", "Edit"),
            Binding("x", "hub_toggle", "Toggle"),
            Binding("u", "filter", "Filter"),
        ]

        def __init__(self, store: object, parent_kind: str, parent_id: int) -> None:
            super().__init__(store)
            self.parent_kind = parent_kind
            self.parent_id = parent_id
            self.title = f"comments · {parent_kind} #{parent_id}"
            self.empty = "No comments or notes. Press a to comment or n to note."
            self.unresolved_only = False

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return (self.parent_kind, self.parent_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            for comment in services.list_comments(self.store, self.parent_kind, self.parent_id):
                if self.unresolved_only and comment.resolved:
                    continue
                state = "resolved" if comment.resolved else "open"
                body = (
                    f"C{comment.id} · {state}\n"
                    f"author @{escape_markup(comment.actor)}\n"
                    f"{escape_markup(comment.text)}"
                )
                out.append(
                    HubEntry(comment.id, f"C{comment.id} {state} {comment.text}", body, "comment")
                )
            for note in services.list_notes(self.store, self.parent_kind, self.parent_id):
                body = f"N{note.id} note\n@{escape_markup(note.actor)}\n{escape_markup(note.text)}"
                out.append(HubEntry(note.id, f"N{note.id} {note.text}", body, "note"))
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                services.add_comment(
                    self.store, self.parent_kind, self.parent_id, text, actor="tui"
                )
                self._reload()

            self.app.push_screen(FilterPromptScreen("Add comment", "review comment", "Add"), cb)

        def note(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                services.add_note(self.store, self.parent_kind, self.parent_id, text, actor="tui")
                self._reload()

            self.app.push_screen(FilterPromptScreen("Add note", "handoff note", "Add"), cb)

        def edit_row(self) -> None:
            entry = self._selected()
            if entry is None or entry.kind != "comment":
                self.notify("select a comment first", timeout=3)
                return
            comment = next(
                (
                    item
                    for item in services.list_comments(self.store, self.parent_kind, self.parent_id)
                    if item.id == entry.oid
                ),
                None,
            )
            if comment is None:
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    self.store.update_comment(comment.id, text, actor="tui")
                except ValueError as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Edit comment", "comment text", "Save", initial=comment.text)
            )

        def action_edit_row(self) -> None:
            self.edit_row()

        def toggle(self) -> None:
            entry = self._selected()
            if entry is None or entry.kind != "comment":
                self.notify("select a comment first", timeout=3)
                return
            comment = next(
                (
                    item
                    for item in services.list_comments(self.store, self.parent_kind, self.parent_id)
                    if item.id == entry.oid
                ),
                None,
            )
            if comment is None:
                return
            services.resolve_comment(
                self.store, comment.id, resolved=not comment.resolved, actor="tui"
            )
            self._reload()

        def filter_toggle(self) -> None:
            self.unresolved_only = not self.unresolved_only
            self._reload()
            self.notify(
                "showing unresolved comments" if self.unresolved_only else "showing everything",
                timeout=3,
            )
