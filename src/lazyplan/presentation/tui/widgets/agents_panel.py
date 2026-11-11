"""The agents pane: active sessions and the last handoff."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from .... import services
from ....core.ports.sessions import SessionsPort
from ...shared.design import EMPTY_AGENTS, EMPTY_AGENTS_HINT, empty_state, escape_markup
from ..views.agents import rank_sessions, session_line, sessions_summary

VISIBLE_SESSIONS = 5
OPEN_SESSIONS_READ = 50


class AgentsPanel(VerticalScroll):
    """Active session rows with the selected plan's last handoff."""

    can_focus = True

    def __init__(self) -> None:
        super().__init__(id="agents")
        self.border_title = " agents "

    def on_click(self) -> None:
        """Open the sessions hub for the selected plan."""
        handler = getattr(self.app, "action_open_sessions_hub", None)
        if callable(handler):
            handler()

    def compose(self) -> ComposeResult:
        yield Static("", id="agents-body")
        yield Static("", id="agents-empty", classes="pane-empty")

    def _show_body(self) -> None:
        """Show the session rows and hide the empty state."""
        self.query_one("#agents-body", Static).display = True
        self.query_one("#agents-empty", Static).display = False

    def show(self, store: SessionsPort, plan_id: int | None = None) -> None:
        body = self.query_one("#agents-body", Static)
        try:
            services.sessions.reap_idle_sessions(store, now=time.time())
        except (OSError, RuntimeError, ValueError):
            pass
        sessions = services.sessions.list_sessions(store, open_only=True, limit=OPEN_SESSIONS_READ)
        if not sessions:
            body.display = False
            empty = self.query_one("#agents-empty", Static)
            empty.display = True
            empty.update(empty_state(EMPTY_AGENTS, EMPTY_AGENTS_HINT))
            self.border_subtitle = ""
            self.scroll_home(animate=False)
            return
        self._show_body()
        stamp = time.time()
        ranked = rank_sessions(sessions, stamp)[:VISIBLE_SESSIONS]
        lines = [session_line(session, stamp) for session in ranked]
        handoff = services.sessions.previous_session(store, plan_id=plan_id)
        if handoff and handoff.get("handoff"):
            lines.append(f"[dim]handoff[/] {escape_markup(str(handoff['handoff']))}")
        body.update("\n".join(lines))
        self.border_subtitle = sessions_summary(sessions, stamp)
        self.scroll_home(animate=False)
