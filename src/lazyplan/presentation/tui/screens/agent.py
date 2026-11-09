"""Agent Workbench: prompt, stream, and stop one ACP run."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from ....store import Store, default_actor
from ..controllers.agent import AgentController
from ..views.agent import AgentTranscript
from .agent_finish import AgentFinishScreen
from .agent_permission import AgentPermissionScreen
from .agent_proposals import ProposalReviewScreen

if TYPE_CHECKING:
    pass


if _TEXTUAL_OK:

    class AgentScreen(Screen):
        """One conversation with one ACP agent."""

        BINDINGS = [
            Binding("escape", "close", "Close", priority=True),
            Binding("ctrl+s", "send", "Send", priority=True),
            Binding("ctrl+x", "cancel", "Stop", priority=True),
            Binding("ctrl+p", "open_proposals", "Proposals", priority=True),
            Binding("ctrl+f", "finish", "Finish", priority=True),
        ]

        navigation_name = "agent"

        def __init__(
            self,
            profile: AgentProfile,
            cwd: str | Path,
            *,
            title: str = "",
            mcp_servers: tuple[dict[str, object], ...] = (),
            store: Store | None = None,
            task_id: int | None = None,
            prompt: str = "",
        ) -> None:
            super().__init__()
            self.profile = profile
            self.cwd = Path(cwd).expanduser().resolve()
            self._title = title or profile.title
            self._mcp_servers = mcp_servers
            self._store = store
            self._task_id = task_id
            self._prompt = prompt
            self._work: dict[str, Any] | None = None
            self._lazy_session_id: int | None = None
            self._agent_run_id: int | None = None
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
                    yield Button("Proposals", id="agent-proposals")
                    yield Button("Finish", id="agent-finish")
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
            self._update_head()
            self._set_status("idle", "not started")
            prompt = self.query_one("#agent-prompt", TextArea)
            if self._prompt:
                prompt.text = self._prompt
            prompt.focus()

        def on_unmount(self) -> None:
            if self._consumer is not None and not self._consumer.done():
                self._consumer.cancel()
            if self._controller is not None:
                asyncio.create_task(self._controller.close())
            if self._store is not None and self._agent_run_id is not None:
                asyncio.create_task(self._close_run_on_exit())

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

        def _update_head(self) -> None:
            if self._work is None:
                self.query_one("#agent-head", Static).update(
                    f"[bold]{self._title}[/]\n[dim]{self.cwd}[/]"
                )
                return
            task = self._work["task"]
            plan = self._work["plan"]
            milestone = self._work["milestone"]
            branch = str(self._work.get("branch") or "current checkout")
            self.query_one("#agent-head", Static).update(
                f"[bold]T{task.id} {task.title}[/] · P{plan.id} {plan.name}\n"
                f"[dim]{milestone.title} · {branch} · {self.cwd}[/]"
            )

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
                if self._task_id is not None and self._store is not None and self._work is None:
                    from ....services.agent_work import start_work

                    self._work = start_work(
                        self._store,
                        self._task_id,
                        actor=default_actor(),
                        cwd=self.cwd,
                    )
                    self._lazy_session_id = int(self._work["session"].id)
                    self._update_head()
                if not self._started:
                    session_id = await self._controller.start()
                    self._started = True
                    if self._task_id is not None and self._store is not None:
                        run = self._store.add_agent_run(
                            session_id,
                            lazyplan_session_id=self._lazy_session_id,
                            plan_id=int(self._work["plan"].id) if self._work else None,
                            task_id=self._task_id,
                            title=f"Work on T{self._task_id}",
                            cwd=str(self.cwd),
                            actor="agent",
                        )
                        self._agent_run_id = int(run["id"])
                await self._controller.prompt(text)
                refresh = getattr(self.app, "refresh_all", None)
                if callable(refresh):
                    refresh("agent turn")
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

        async def _close_run_on_exit(self) -> None:
            if self._store is None or self._agent_run_id is None:
                return
            from ....services.agent_work import finish_work

            try:
                finish_work(
                    self._store,
                    self._agent_run_id,
                    actor=default_actor(),
                    summary="workbench closed",
                    handoff="",
                )
            except (KeyError, ValueError):
                pass

        async def _reject_pending_permission(self) -> None:
            permission = self._active_permission
            if permission is None or self._controller is None:
                return
            self._active_permission = None
            self._permission_open = False
            await self._controller.reply_permission(permission.request_id, None)

        def action_finish(self) -> None:
            if self._store is None or self._agent_run_id is None:
                self.notify("no active work run to finish")
                return
            self.app.push_screen(AgentFinishScreen(), self._finish_run)

        def _finish_run(self, result: tuple[str, str] | None) -> None:
            if result is None or self._store is None or self._agent_run_id is None:
                return
            summary, handoff = result
            from .... import services
            from ....services.agent_work import finish_work

            if self._task_id is not None:
                try:
                    services.finish_task(
                        self._store,
                        self._task_id,
                        actor=default_actor(),
                        require_pr=True,
                        require_checks=True,
                        require_evidence=True,
                    )
                except services.GateError as exc:
                    self.notify(f"finish blocked: {exc}", severity="error", timeout=6)
                    return
                except (ValueError, KeyError) as exc:
                    self.notify(f"finish blocked: {exc}", severity="error", timeout=6)
                    return
            try:
                finish_work(
                    self._store,
                    self._agent_run_id,
                    actor=default_actor(),
                    summary=summary,
                    handoff=handoff,
                )
            except (KeyError, ValueError) as exc:
                self.notify(f"error: {exc}")
                return
            self._transcript.add_notice("work session finished")
            self._agent_run_id = None
            self._work = None
            self._update_head()
            self._render_transcript()
            refresh = getattr(self.app, "refresh_all", None)
            if callable(refresh):
                refresh("agent run finished")

        def action_open_proposals(self) -> None:
            if self._store is None:
                self.notify("no database for proposals")
                return
            self.app.push_screen(ProposalReviewScreen(self._store))

        async def action_cancel(self) -> None:
            await self._reject_pending_permission()
            if self._controller is not None:
                await self._controller.cancel()

        async def action_close(self) -> None:
            if self._agent_run_id is not None:
                self.action_finish()
                return
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
            elif event.button.id == "agent-proposals":
                self.action_open_proposals()
            elif event.button.id == "agent-finish":
                self.action_finish()
            elif event.button.id == "agent-close":
                await self.action_close()
