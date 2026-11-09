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

from ....infrastructure.agents import AgentEvent, AgentProfile, PermissionRequest
from ..controllers.agent import AgentController
from ..views.agent import AgentTranscript
from .agent_permission import AgentPermissionScreen

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
            mcp_servers: tuple[dict[str, object], ...] = (),
        ) -> None:
            super().__init__()
            self.profile = profile
            self.cwd = Path(cwd).expanduser().resolve()
            self._title = title or profile.title
            self._mcp_servers = mcp_servers
            self._controller: AgentController | None = None
            self._queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
            self._consumer: asyncio.Task[None] | None = None
            self._transcript = AgentTranscript()
            self._usage = ""
            self._started = False
            self._permission_queue: list[PermissionRequest] = []
            self._permission_open = False
            self._active_permission: PermissionRequest | None = None

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
                mcp_servers=self._mcp_servers,
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
            setter = getattr(self.app, "set_agent_status", None)
            if callable(setter):
                setter(status, detail)

        @property
        def transcript(self) -> str:
            """The rendered markdown transcript, for tests and copying."""
            return self._transcript.markdown()

        def _render_transcript(self) -> None:
            self.query_one("#agent-transcript", Markdown).update(self.transcript)

        async def _apply_event(self, event: AgentEvent) -> None:
            if event.kind == "text":
                self._transcript.add_text(event.text)
            elif event.kind == "thought":
                self._transcript.add_thought(event.text)
            elif event.kind in {"tool_call", "tool_update"} and event.tool is not None:
                self._transcript.add_tool(event.tool, event.payload)
                if event.tool.status == "failed":
                    name = event.tool.title or event.tool.name or "tool"
                    self._transcript.add_notice(f"{name} failed")
            elif event.kind == "plan":
                self._transcript.add_plan(event.plan)
            elif event.kind == "usage" and event.usage is not None:
                cost = ""
                if event.usage.amount is not None:
                    cost = f" · {event.usage.amount:.4f} {event.usage.currency}".rstrip()
                self._usage = f"{event.usage.used}/{event.usage.size} tokens{cost}"
                if self._controller is not None:
                    self._set_status(self._controller.status, self._controller.detail)
            elif event.kind == "permission" and event.permission is not None:
                self._transcript.add_permission(event.permission.tool)
                self._permission_queue.append(event.permission)
                self._show_permission()
            elif event.kind == "exit":
                self._transcript.add_exit()
            elif event.kind == "notice":
                self._transcript.add_notice(str(event.payload.get("title", "notice")))
            elif event.kind == "unknown":
                name = str(
                    event.payload.get("sessionUpdate") or event.payload.get("method") or "update"
                )
                self._transcript.add_unknown(name)
            self._render_transcript()

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
            self._transcript.add_user(text)
            try:
                if not self._started:
                    await self._controller.start()
                    self._started = True
                await self._controller.prompt(text)
            except Exception as exc:
                self._transcript.add_error(str(exc))
                self.notify(f"agent error: {exc}")

        def _show_permission(self) -> None:
            if self._permission_open or not self._permission_queue:
                return
            permission = self._permission_queue.pop(0)
            self._active_permission = permission
            self._permission_open = True
            self.app.push_screen(
                AgentPermissionScreen(permission),
                self._permission_reply,
            )

        def _permission_reply(self, option_id: str | None) -> None:
            permission = self._active_permission
            self._active_permission = None
            self._permission_open = False
            if permission is not None and self._controller is not None:
                asyncio.create_task(
                    self._controller.reply_permission(permission.request_id, option_id)
                )
            self.call_after_refresh(self._show_permission)

        async def _reject_pending_permission(self) -> None:
            permission = self._active_permission
            if permission is None or self._controller is None:
                return
            self._active_permission = None
            self._permission_open = False
            await self._controller.reply_permission(permission.request_id, None)

        async def action_cancel(self) -> None:
            await self._reject_pending_permission()
            if self._controller is not None:
                await self._controller.cancel()

        async def action_close(self) -> None:
            await self._reject_pending_permission()
            if self._controller is not None:
                await self._controller.close()
            setter = getattr(self.app, "set_agent_status", None)
            if callable(setter):
                setter("idle", "W workbench")
            self.app.pop_screen()

        async def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "agent-send":
                await self.action_send()
            elif event.button.id == "agent-stop":
                await self.action_cancel()
            elif event.button.id == "agent-close":
                await self.action_close()
