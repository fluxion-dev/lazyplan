"""Agent Workbench: prompt, stream, and stop one ACP run."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Button, Markdown, Static, TextArea

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ....infrastructure.agents import AgentEvent, AgentProfile
from ..controllers.agent import AgentController

if TYPE_CHECKING:
    pass


if _TEXTUAL_OK:

    class AgentScreen(Screen):
        """One conversation with one ACP agent."""

        BINDINGS = [
            Binding("escape", "close", "Close", priority=True),
            Binding("ctrl+s", "send", "Send", priority=True),
            Binding("ctrl+x", "cancel", "Stop", priority=True),
        ]

        navigation_name = "agent"

        def __init__(
            self,
            profile: AgentProfile,
            cwd: str | Path,
            *,
            title: str = "",
        ) -> None:
            super().__init__()
            self.profile = profile
            self.cwd = Path(cwd).expanduser().resolve()
            self._title = title or profile.title
            self._controller: AgentController | None = None
            self._queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
            self._consumer: asyncio.Task[None] | None = None
            self._markdown = ""
            self._agent_open = False
            self._started = False

        def compose(self) -> ComposeResult:
            with Vertical(id="agent-page"):
                yield Static("", id="agent-head")
                with VerticalScroll(id="agent-scroll"):
                    yield Markdown("", id="agent-transcript")
                yield Static("", id="agent-status")
                yield TextArea("", id="agent-prompt")
                with Horizontal(id="agent-actions", classes="btn-row"):
                    yield Button("Send", id="agent-send", variant="primary")
                    yield Button("Stop", id="agent-stop")
                    yield Button("Close", id="agent-close")

        def on_mount(self) -> None:
            self._controller = AgentController(
                self.profile,
                self.cwd,
                on_event=self._enqueue_event,
                on_status=self._enqueue_status,
            )
            self._consumer = asyncio.create_task(self._consume())
            self.query_one("#agent-head", Static).update(
                f"[bold]{self._title}[/]\n[dim]{self.cwd}[/]"
            )
            self._set_status("idle", "not started")
            self.query_one("#agent-prompt", TextArea).focus()

        def on_unmount(self) -> None:
            if self._consumer is not None and not self._consumer.done():
                self._consumer.cancel()
            if self._controller is not None:
                asyncio.create_task(self._controller.close())

        def _enqueue_event(self, event: AgentEvent) -> None:
            self._queue.put_nowait(("event", event))

        def _enqueue_status(self, status: str, detail: str) -> None:
            self._queue.put_nowait(("status", (status, detail)))

        async def _consume(self) -> None:
            while True:
                kind, payload = await self._queue.get()
                if kind == "event":
                    assert isinstance(payload, AgentEvent)
                    await self._apply_event(payload)
                else:
                    assert isinstance(payload, tuple) and len(payload) == 2
                    self._set_status(str(payload[0]), str(payload[1]))

        def _set_status(self, status: str, detail: str = "") -> None:
            label = status if not detail else f"{status} · {detail}"
            self.query_one("#agent-status", Static).update(f"[dim]agent[/] {label}")

        def _write(self, fragment: str) -> None:
            if not fragment:
                return
            self._markdown += fragment
            self.query_one("#agent-transcript", Markdown).update(self._markdown)

        async def _apply_event(self, event: AgentEvent) -> None:
            if event.kind == "text":
                if not self._agent_open:
                    self._write("\n\n**Agent**\n\n")
                    self._agent_open = True
                self._write(event.text)
            elif event.kind == "thought":
                self._write(f"\n\n_{event.text}_\n")
            elif event.kind == "tool_call" and event.tool is not None:
                self._agent_open = False
                self._write(
                    f"\n\n> **{event.tool.title or event.tool.name or 'tool'}**"
                    f" `{event.tool.kind}` · {event.tool.status}\n"
                )
            elif event.kind == "tool_update" and event.tool is not None:
                self._write(f"> {event.tool.status}\n")
            elif event.kind == "plan":
                self._agent_open = False
                rows = "\n".join(f"> {entry.status} · {entry.content}" for entry in event.plan)
                self._write(f"\n\n**Plan**\n\n{rows}\n")
            elif event.kind == "usage" and event.usage is not None:
                cost = ""
                if event.usage.amount is not None:
                    cost = f" · {event.usage.amount:.4f} {event.usage.currency}".rstrip()
                self._set_status(
                    self._controller.status if self._controller is not None else "running",
                    f"{event.usage.used}/{event.usage.size} tokens{cost}",
                )
            elif event.kind == "permission" and event.permission is not None:
                self._write(
                    "\n\n> **Permission requested**\n"
                    f"> {event.permission.tool.title or event.permission.tool.name}\n"
                )
            elif event.kind == "exit":
                self._agent_open = False
                self._write("\n\n_agent exited_\n")
            elif event.kind == "notice":
                self._write(f"\n\n> {event.payload.get('title', 'notice')}\n")
            elif event.kind == "unknown":
                self._write("")

        async def action_send(self) -> None:
            if self._controller is None:
                return
            prompt = self.query_one("#agent-prompt", TextArea)
            text = prompt.text.strip()
            if not text:
                self.notify("type a prompt first")
                return
            if self._controller.status in {"starting", "running", "waiting"}:
                self.notify("one prompt is already running")
                return
            prompt.text = ""
            self._write(f"\n\n**You**\n\n{text}")
            self._agent_open = False
            try:
                if not self._started:
                    await self._controller.start()
                    self._started = True
                await self._controller.prompt(text)
            except Exception as exc:
                self._write(f"\n\n**Error**\n\n{exc}\n")
                self.notify(f"agent error: {exc}")

        async def action_cancel(self) -> None:
            if self._controller is not None:
                await self._controller.cancel()

        async def action_close(self) -> None:
            if self._controller is not None:
                await self._controller.close()
            self.app.pop_screen()

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "agent-send":
                await self.action_send()
            elif event.button.id == "agent-stop":
                await self.action_cancel()
            elif event.button.id == "agent-close":
                await self.action_close()
