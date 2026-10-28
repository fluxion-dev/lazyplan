"""Local MCP server: JSON-RPC 2.0 over stdio.

Stdlib only. Protocol frames go to stdout; diagnostics go to stderr. Tools and
resources reuse the same store/services as the CLI.
"""

from __future__ import annotations

import json

from .. import brief
from .base import McpBase


class ResourcesMixin(McpBase):
    """MCP resource listing and reads."""

    def _read_resource(self, request_id: object, params: dict) -> dict:
        uri = params.get("uri")
        if not isinstance(uri, str):
            return self._error(request_id, -32602, "resource uri is required")
        try:
            store = self._need_store()
            if uri == "lazyplan://brief":
                payload: object = brief.build(store)
            elif uri.startswith("lazyplan://plan/"):
                plan_id = int(uri.rsplit("/", 1)[-1])
                payload = store.get_full("plan", plan_id)
                if payload is None:
                    raise KeyError(f"plan {plan_id} not found")
            else:
                return self._error(request_id, -32002, f"resource not found: {uri}")
        except (KeyError, ValueError, RuntimeError) as exc:
            return self._error(request_id, -32002, str(exc))
        return self._result(
            request_id,
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(payload, indent=2, default=str),
                    }
                ]
            },
        )

    def resources(self) -> list[dict]:
        """Resource definitions."""
        return [
            {
                "uri": "lazyplan://brief",
                "name": "Session brief",
                "mimeType": "application/json",
            },
            {
                "uri": "lazyplan://plan/1",
                "name": "Plan document",
                "mimeType": "application/json",
            },
        ]
