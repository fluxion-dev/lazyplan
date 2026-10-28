"""MCP session core: protocol, resources, and transport."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, TextIO

from ..store import Store

PROTOCOL_VERSION = "2024-11-05"


class McpBase:
    """MCP session core: protocol, resources, and transport."""

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

    def _result(self, request_id: object, result: object) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: object, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

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

    if TYPE_CHECKING:

        def tools(self) -> list[dict]:
            raise NotImplementedError

        def _call_tool(self, request_id: object, params: dict) -> dict:
            raise NotImplementedError

        def resources(self) -> list[dict]:
            raise NotImplementedError

        def _read_resource(self, request_id: object, params: dict) -> dict:
            raise NotImplementedError

    def _need_store(self) -> Store:
        if self.store is None:
            raise RuntimeError("no database")
        return self.store
