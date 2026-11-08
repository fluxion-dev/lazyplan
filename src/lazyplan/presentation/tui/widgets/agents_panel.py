"""The agents pane: active sessions and the last handoff."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from .... import services
from ....core.entities import Session
from ....core.ports.sessions import SessionsReadPort
from ...shared.design import EMPTY_AGENTS, EMPTY_AGENTS_HINT, escape_markup


def _age(started_at: float, stamp: float) -> str:
    minutes = int(max(0.0, stamp - started_at) / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


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

    def show(self, store: SessionsReadPort, plan_id: int | None = None) -> None:
        body = self.query_one("#agents-body", Static)
        sessions = services.sessions.list_sessions(store, open_only=True, limit=5)
        if not sessions:
            body.remove_class("agents-error")
            body.add_class("agents-empty")
            body.update(f"[bold]{EMPTY_AGENTS}[/]\n[dim]{EMPTY_AGENTS_HINT}[/]")
            self.border_subtitle = ""
            self.scroll_home(animate=False)
            return
        stamp = time.time()
        lines = [self._session_line(session, stamp) for session in sessions]
        handoff = services.sessions.previous_session(store, plan_id=plan_id)
        if handoff and handoff.get("handoff"):
            lines.append(f"[dim]handoff[/] {escape_markup(str(handoff['handoff']))}")
        body.remove_class("agents-empty", "agents-error")
        body.update("\n".join(lines))
        self.border_subtitle = f"{len(sessions)} active"
        self.scroll_home(animate=False)

    @staticmethod
    def _session_line(session: Session, stamp: float) -> str:
        started = time.strftime("%H:%M", time.localtime(session.started_at))
        plan = f"P{session.plan_id}" if session.plan_id is not None else "no plan"
        branch = escape_markup(session.branch) if session.branch else "no branch"
        return (
            f"[bold]@{escape_markup(session.actor)}[/] [dim]S{session.id}[/] · "
            f"[dim]{plan}[/] · {branch} · [dim]{started} · {_age(session.started_at, stamp)}[/]"
        )
