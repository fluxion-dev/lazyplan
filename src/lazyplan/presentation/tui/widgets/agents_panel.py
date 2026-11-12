"""The agents pane: active sessions and the last handoff."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from .... import services
from ....core.entities import Session
from ....core.ports.sessions import SessionsPort
from ...shared.design import (
    EMPTY_AGENTS,
    EMPTY_AGENTS_HINT,
    empty_state,
    escape_markup,
    spinner_enabled,
)
from ...shared.session_labels import plan_names
from ..views.agents import rank_sessions, session_line, sessions_summary

OPEN_SESSIONS_READ = 50


class AgentsPanel(VerticalScroll):
    """Active session rows with the selected plan's last handoff."""

    can_focus = False

    def __init__(self) -> None:
        super().__init__(id="agents")
        self.border_title = " agents "
        self._sessions: list[Session] = []
        self._titles: dict[int, str] = {}
        self._stamp = 0.0
        self._handoff = ""
        self._frame: int | None = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="agents-body")
        yield Static("", id="agents-empty", classes="pane-empty")

    def _show_body(self) -> None:
        """Show the session rows and hide the empty state."""
        self.query_one("#agents-body", Static).display = True
        self.query_one("#agents-empty", Static).display = False

    def _row_width(self) -> int | None:
        """Content cells available to one row, or None before the first layout."""
        body = self.query_one("#agents-body", Static)
        width = body.size.width or self.size.width - 2
        return width if width > 0 else None

    def show(self, store: SessionsPort, plan_id: int | None = None) -> None:
        body = self.query_one("#agents-body", Static)
        try:
            services.sessions.reap_idle_sessions(store, now=time.time())
        except (OSError, RuntimeError, ValueError):
            pass
        sessions = services.sessions.list_sessions(store, open_only=True, limit=OPEN_SESSIONS_READ)
        if not sessions:
            self._sessions = []
            self._titles = {}
            self._handoff = ""
            self._frame = None
            body.display = False
            empty = self.query_one("#agents-empty", Static)
            empty.display = True
            empty.update(empty_state(EMPTY_AGENTS, EMPTY_AGENTS_HINT))
            self.border_subtitle = ""
            self.scroll_home(animate=False)
            return
        self._show_body()
        self._stamp = time.time()
        self._sessions = rank_sessions(sessions, self._stamp)
        self._titles = plan_names(store)
        handoff = services.sessions.previous_session(store, plan_id=plan_id)
        note = str(handoff["handoff"]) if handoff and handoff.get("handoff") else ""
        self._handoff = f"[dim]handoff[/] {escape_markup(note)}" if note else ""
        self._frame = 0 if spinner_enabled() else None
        self._paint_rows()
        self.border_subtitle = sessions_summary(sessions, self._stamp)
        self.scroll_home(animate=False)

    def has_working(self) -> bool:
        """True while a cached session is still in its working phase."""
        if not self._sessions:
            return False
        stamp = time.time()
        return any(
            services.session_state(session, stamp) == "working" for session in self._sessions
        )

    def advance(self, frame: int) -> bool:
        """Paint the cached rows at *frame* without another store read."""
        if not self._sessions or not spinner_enabled():
            return False
        if not self.has_working():
            return False
        self._frame = frame
        self._paint_rows()
        return True

    def _paint_rows(self) -> None:
        width = self._row_width()
        stamp = time.time()
        lines = [
            session_line(
                session,
                stamp,
                plan_title=self._titles.get(session.plan_id or 0, ""),
                width=width,
                frame=self._frame,
            )
            for session in self._sessions
        ]
        if self._handoff:
            lines.append(self._handoff)
        self.query_one("#agents-body", Static).update("\n".join(lines))
