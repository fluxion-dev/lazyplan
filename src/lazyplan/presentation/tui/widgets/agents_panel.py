"""The agents pane: exact live registry rows and the last handoff."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from .... import services
from ....core.entities import Agent
from ....core.ports.agents import AgentsPort
from ...shared.design import escape_markup
from ...shared.session_labels import plan_names
from ..query import query_one_opt
from ..views.agents import agent_line, agents_summary, rank_agents

OPEN_AGENTS_READ = 50


class AgentsPanel(VerticalScroll):
    """Live agent rows with the selected plan's last handoff."""

    can_focus = False

    def __init__(self) -> None:
        super().__init__(id="agents")
        self.border_title = " agents "
        self.display = False
        self._agents: list[Agent] = []
        self._titles: dict[int, str] = {}
        self._stamp = 0.0
        self._handoff = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="agents-body")

    def _row_width(self) -> int | None:
        """Content cells available to one row, or None before the first layout."""
        body = query_one_opt(self, "#agents-body", Static)
        width = (body.size.width if body is not None else self.size.width) or self.size.width - 2
        return width if width > 0 else None

    def show(self, store: AgentsPort, plan_id: int | None = None) -> None:
        try:
            services.sweep_lost(store)
        except (OSError, RuntimeError, ValueError):
            pass
        agents = store.list_agents(open_only=True, limit=OPEN_AGENTS_READ)
        if not agents:
            self._agents = []
            self._titles = {}
            self._handoff = ""
            self.display = False
            self.border_subtitle = ""
            self.scroll_home(animate=False)
            return
        self.display = True
        self._stamp = time.time()
        self._agents = rank_agents(agents, self._stamp)
        self._titles = plan_names(store)
        handoff = services.previous_agent(store, plan_id=plan_id)
        note = str(handoff["handoff"]) if handoff and handoff.get("handoff") else ""
        self._handoff = f"[dim]handoff[/] {escape_markup(note)}" if note else ""
        self._paint_rows()
        self.border_subtitle = agents_summary(agents, self._stamp)
        self.scroll_home(animate=False)

    def _paint_rows(self) -> None:
        body = query_one_opt(self, "#agents-body", Static)
        if body is None:
            return
        width = self._row_width()
        stamp = time.time()
        lines = [
            agent_line(
                agent,
                stamp,
                plan_title=self._titles.get(agent.plan_id or 0, ""),
                width=width,
            )
            for agent in self._agents
        ]
        if self._handoff:
            lines.append(self._handoff)
        body.update("\n".join(lines))
