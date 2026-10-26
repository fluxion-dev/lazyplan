"""Local MCP server: JSON-RPC 2.0 over stdio.

Stdlib only. Protocol frames go to stdout; diagnostics go to stderr. Tools and
resources reuse the same store/services as the CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from .store import Store

PROTOCOL_VERSION = "2024-11-05"


class McpServer:
    """One local MCP session bound to one database and actor."""

    def __init__(
        self,
        store: Store | None,
        actor: str = "human",
        read_only: bool = False,
        db_path: str = "",
    ) -> None:
        self.store = store
        self.actor = actor
        self.read_only = read_only
        self.db_path = db_path

    # -- protocol -----------------------------------------------------
    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _result(self, request_id: object, result: object) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def handle(self, request: object) -> dict | None:
        """Handle one decoded request; None for notifications."""
        if not isinstance(request, dict):
            return self._error(None, -32600, "invalid request")
        request_id = request.get("id")
        method = request.get("method")
        if not isinstance(method, str):
            return self._error(request_id, -32600, "missing method")
        params = request.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            return self._error(request_id, -32602, "params must be an object")
        if request_id is None:
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False, "subscribe": False},
                    },
                    "serverInfo": {"name": "lazyplan", "version": "0"},
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self.tools()})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        if method == "resources/list":
            return self._result(request_id, {"resources": self.resources()})
        if method == "resources/read":
            return self._read_resource(request_id, params)
        return self._error(request_id, -32601, f"method not found: {method}")

    # -- protocol surface --------------------------------------------
    def tools(self) -> list[dict]:
        """Tool definitions; write tools appear only outside read-only mode."""
        return []

    def resources(self) -> list[dict]:
        """Resource definitions."""
        return []

    def _call_tool(self, request_id: object, params: dict) -> dict:
        name = params.get("name")
        if not isinstance(name, str):
            return self._error(request_id, -32602, "tool name is required")
        return self._error(request_id, -32601, f"tool not found: {name}")

    def _read_resource(self, request_id: object, params: dict) -> dict:
        uri = params.get("uri")
        if not isinstance(uri, str):
            return self._error(request_id, -32602, "resource uri is required")
        return self._error(request_id, -32002, f"resource not found: {uri}")

    # -- loop ---------------------------------------------------------
    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> int:
        """Read JSON-RPC frames until EOF; never crash the loop."""
        source = stdin or sys.stdin
        sink = stdout or sys.stdout
        for line in source:
            line = line.strip()
            if not line:
                continue
            response: dict | None
            try:
                request = json.loads(line)
            except ValueError:
                response = self._error(None, -32700, "parse error")
            else:
                try:
                    response = self.handle(request)
                except Exception as exc:  # keep the session alive
                    response = self._error(
                        request.get("id") if isinstance(request, dict) else None,
                        -32603,
                        f"internal error: {exc}",
                    )
            if response is None:
                continue
            sink.write(json.dumps(response, separators=(",", ":"), default=str) + "\n")
            sink.flush()
        return 0


def build_server(db_path: str, actor: str = "human", read_only: bool = False) -> McpServer:
    """Open or skip the database according to the mode."""
    path = Path(db_path).expanduser()
    if read_only and not path.is_file():
        return McpServer(None, actor=actor, read_only=True, db_path=str(path))
    return McpServer(Store(str(path)), actor=actor, read_only=read_only, db_path=str(path))


def run(db_path: str, actor: str, read_only: bool = False) -> int:
    """Entry point used by the CLI."""
    return build_server(db_path, actor=actor, read_only=read_only).serve()
