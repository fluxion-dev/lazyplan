"""Shared MCP tool schema helpers."""

from __future__ import annotations

import json


def id_schema() -> dict:
    return {"type": "integer"}


def str_schema() -> dict:
    return {"type": "string"}


def kind_schema() -> dict:
    return {"type": "string", "enum": ["plan", "milestone", "task"]}


def tool(
    name: str,
    description: str,
    properties: dict,
    required: list[str] | None = None,
    read_only: bool = True,
) -> dict:
    """Build one MCP tool definition."""
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        "annotations": {"readOnlyHint": read_only},
    }


def ok(payload: object) -> dict:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, indent=2, default=str),
            }
        ]
    }


def error(message: str) -> dict:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
