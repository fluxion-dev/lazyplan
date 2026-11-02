"""Byte-exact MCP discovery contract for tools and resources."""

from __future__ import annotations

import json
import unittest
from typing import Any

from lazyplan.presentation import mcp
from tests.support.paths import ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "mcp" / "schema.json"


def _call(server: mcp.McpServer, method: str) -> dict[str, Any]:
    """Return one JSON-RPC result envelope."""
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": method})
    assert response is not None
    return response["result"]


def discovery(server: mcp.McpServer) -> dict[str, Any]:
    """Return the discoverable MCP surface in a deterministic shape."""
    return {
        "tools": _call(server, "tools/list")["tools"],
        "resources": _call(server, "resources/list")["resources"],
    }


class TestMcpSchemaBaseline(unittest.TestCase):
    """Every MCP surface keeps returning the pre-refactor schema."""

    def test_discovery_schema_is_pinned(self) -> None:
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        actual = json.loads(json.dumps(discovery(mcp.McpServer(None)), sort_keys=True))
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
