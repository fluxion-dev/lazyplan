"""Agent runtime: one ACP agent process and one active prompt."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..infrastructure.agents import AcpClient, AgentProfile


def lazyplan_mcp_server(
    db_path: str | Path,
    *,
    read_only: bool = False,
) -> dict[str, Any]:
    """The stdio MCP server config passed to an ACP session."""
    args = [sys.executable, "-m", "lazyplan", "--db", str(Path(db_path)), "mcp"]
    if read_only:
        args.append("--read-only")
    return {
        "name": "lazyplan",
        "command": args[0],
        "args": args[1:],
        "env": [],
    }


class AgentRuntime:
    """Own one ACP process for the workbench."""

    def __init__(
        self,
        profile: AgentProfile,
        cwd: str | Path,
        *,
        mcp_servers: Sequence[dict[str, Any]] = (),
    ) -> None:
        self.profile = profile
        self.cwd = Path(cwd).expanduser().resolve()
        self.mcp_servers = tuple(dict(server) for server in mcp_servers)
        self.client = AcpClient(
            profile.command,
            self.cwd,
            env={**os.environ, **profile.env},
        )
        self.session_id = ""
        self._started = False
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    async def start(self) -> str:
        """Start the process, initialize ACP, and create one session."""
        if self._started:
            return self.session_id
        await self.client.start()
        await self.client.initialize()
        self.session_id = await self.client.new_session(
            cwd=self.cwd,
            mcp_servers=self.mcp_servers,
        )
        self._started = True
        return self.session_id

    async def prompt(self, text: str) -> dict[str, Any]:
        """Send one prompt; reject a concurrent prompt."""
        if not self._started:
            await self.start()
        if self._busy:
            raise RuntimeError("one prompt is already running")
        self._busy = True
        try:
            return await self.client.prompt(self.session_id, text)
        finally:
            self._busy = False

    async def cancel(self) -> None:
        """Cancel the active prompt, if any."""
        if self._started:
            await self.client.cancel(self.session_id)

    async def reply_permission(self, request_id: int | str, option_id: str | None) -> None:
        """Answer one ACP permission request."""
        await self.client.reply_permission(request_id, option_id)

    async def close(self) -> None:
        """Close the session and the process."""
        if self._started:
            await self.client.close_session(self.session_id)
        await self.client.close()
        self._started = False
