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

from ....infrastructure.agents import AgentEvent, AgentProfile, ToolCall
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
            self._blocks: list[str] = []
            self._kinds: list[str] = []
            self._tool_blocks: dict[str, int] = {}
            self._tools: dict[str, ToolCall] = {}
            self._plan_block: int | None = None
            self._usage = ""
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
            if self._usage:
                label += f" · {self._usage}"
            self.query_one("#agent-status", Static).update(f"[dim]agent[/] {label}")

        @property
        def transcript(self) -> str:
            """The rendered markdown transcript, for tests and copying."""
            return "\n\n".join(self._blocks)

        def _render_transcript(self) -> None:
            self.query_one("#agent-transcript", Markdown).update(self.transcript)

        def _append(self, text: str, kind: str) -> int:
            self._blocks.append(text)
            self._kinds.append(kind)
            self._render_transcript()
            return len(self._blocks) - 1

        def _write_text(self, text: str) -> None:
            if text and self._kinds and self._kinds[-1] == "agent":
                self._blocks[-1] += text
                self._render_transcript()
            elif text:
                self._append(f"**Agent**\n\n{text}", "agent")

        @staticmethod
        def _tool_card(tool: ToolCall) -> str:
            lines = [f"**{tool.title or tool.name or 'tool'}** `{tool.kind}` · {tool.status}"]
            for item in tool.content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "diff":
                    path = item.get("path") or "file"
                    new_text = str(item.get("newText") or "").strip()
                    lines.append(f"`{path}`")
                    if new_text:
                        lines.append(f"```\n{new_text[:1200]}\n```")
                elif item.get("type") == "content":
                    inner = item.get("content")
                    if isinstance(inner, dict) and inner.get("type") == "text":
                        lines.append(str(inner.get("text") or "")[:1200])
            return "\n".join(line for line in lines if line)

        async def _apply_event(self, event: AgentEvent) -> None:
            if event.kind == "text":
                self._write_text(event.text)
            elif event.kind == "thought":
                self._append(f"_{event.text}_", "thought")
            elif event.kind in {"tool_call", "tool_update"} and event.tool is not None:
                tool = event.tool
                previous = self._tools.get(tool.tool_call_id)
                if previous is not None:
                    tool = previous.merged(event.payload)
                self._tools[tool.tool_call_id] = tool
                card = self._tool_card(tool)
                index = self._tool_blocks.get(tool.tool_call_id)
                if index is None:
                    index = self._append(card, "tool")
                    self._tool_blocks[tool.tool_call_id] = index
                else:
                    self._blocks[index] = card
                    self._render_transcript()
            elif event.kind == "plan":
                rows = "\n".join(f"> {entry.status} · {entry.content}" for entry in event.plan)
                block = f"**Plan**\n\n{rows}"
                if self._plan_block is None:
                    self._plan_block = self._append(block, "plan")
                else:
                    self._blocks[self._plan_block] = block
                    self._render_transcript()
            elif event.kind == "usage" and event.usage is not None:
                cost = ""
                if event.usage.amount is not None:
                    cost = f" · {event.usage.amount:.4f} {event.usage.currency}".rstrip()
                self._usage = f"{event.usage.used}/{event.usage.size} tokens{cost}"
                if self._controller is not None:
                    self._set_status(self._controller.status, self._controller.detail)
            elif event.kind == "permission" and event.permission is not None:
                self._append(
                    "> **Permission requested**\n"
                    f"> {event.permission.tool.title or event.permission.tool.name}",
                    "permission",
                )
            elif event.kind == "exit":
                self._append("_agent exited_", "exit")
            elif event.kind == "notice":
                self._append(f"> {event.payload.get('title', 'notice')}", "notice")
            elif event.kind == "unknown":
                name = event.payload.get("sessionUpdate") or event.payload.get("method") or "update"
                self._append(f"> unknown agent update: {name}", "unknown")

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
            self._append(f"**You**\n\n{text}", "user")
            try:
                if not self._started:
                    await self._controller.start()
                    self._started = True
                await self._controller.prompt(text)
            except Exception as exc:
                self._append(f"**Error**\n\n{exc}", "error")
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
