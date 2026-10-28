"""Local MCP server: JSON-RPC 2.0 over stdio."""

from __future__ import annotations

from pathlib import Path

from ..store import Store
from .base import McpBase
from .resources import ResourcesMixin
from .tools import ToolsMixin


class McpServer(ToolsMixin, ResourcesMixin, McpBase):
    """One local MCP session bound to one database and actor."""


def build_server(db_path: str, actor: str = "human", read_only: bool = False) -> McpServer:
    """Open or skip the database according to the mode."""
    path = Path(db_path).expanduser()
    if read_only and not path.is_file():
        return McpServer(None, actor=actor, read_only=True, db_path=str(path))
    return McpServer(Store(str(path)), actor=actor, read_only=read_only, db_path=str(path))


def run(db_path: str, actor: str, read_only: bool = False) -> int:
    """Entry point used by the CLI."""
    return build_server(db_path, actor=actor, read_only=read_only).serve()
