"""TUI-side agent run: status, prompt submission, and event fan-out."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ....infrastructure.agents import AgentEvent, AgentProfile
from ....services.agents import AgentRuntime

StatusCallback = Callable[[str, str], None]
EventCallback = Callable[[AgentEvent], None]


class AgentController:
    """Own one workbench run without importing Textual."""

    def __init__(
        self,
        profile: AgentProfile,
        cwd: str | Path,
        *,
        on_event: EventCallback,
        on_status: StatusCallback,
        mcp_servers: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.profile = profile
        self.runtime = AgentRuntime(profile, cwd, mcp_servers=mcp_servers)
        self.on_event = on_event
        self.on_status = on_status
        self.status = "idle"
        self.detail = ""
        self._pump_task: asyncio.Task[None] | None = None

    def set_status(self, status: str, detail: str = "") -> None:
        """Update and publish the run status."""
        self.status = status
        self.detail = detail
        self.on_status(status, detail)

    async def start(self) -> str:
        """Start the agent and begin forwarding its events."""
        self.set_status("starting")
        try:
            session_id = await self.runtime.start()
        except Exception as exc:
            self.set_status("error", str(exc))
            raise
        self._pump_task = asyncio.create_task(self._pump())
        self.set_status("idle", self.profile.title)
        return session_id

    async def _pump(self) -> None:
        try:
            async for event in self.runtime.client.events():
                if event.kind == "permission":
                    self.set_status("waiting", "permission needed")
                elif event.kind == "exit":
                    self.set_status("closed")
                self.on_event(event)
        except asyncio.CancelledError:
            raise

    async def prompt(self, text: str) -> dict[str, Any]:
        """Send a prompt and return its stop reason."""
        self.set_status("running")
        try:
            result = await self.runtime.prompt(text)
        except Exception as exc:
            self.set_status("error", str(exc))
            raise
        self.set_status("idle", self.profile.title)
        return result

    async def cancel(self) -> None:
        """Cancel the active prompt."""
        await self.runtime.cancel()

    async def reply_permission(self, request_id: int | str, option_id: str | None) -> None:
        """Answer a permission request and resume the run."""
        await self.runtime.reply_permission(request_id, option_id)
        self.set_status("running", "permission answered")

    async def close(self) -> None:
        """Stop the pump and the process."""
        await self.runtime.close()
        if self._pump_task is not None and not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
        self.set_status("closed")
