"""A scripted ACP v1 agent for transport tests.

Run as a subprocess; it never imports lazyplan and never touches the network.
Scenarios are selected with `FAKE_ACP_SCENARIO`:

- `text`: stream text and one tool call.
- `permission`: ask for permission, then finish after the reply.
- `cancel`: stream text and finish as cancelled when asked.
- `crash`: exit while a prompt is active.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

SCENARIO = os.environ.get("FAKE_ACP_SCENARIO", "text")
CRLF = bool(os.environ.get("FAKE_ACP_CRLF"))
SESSION = "sess_test"
PERMISSION_ID = 900
MCP_NAMES: list[str] = []


def send(payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    separator = "\r\n" if CRLF else "\n"
    sys.stdout.buffer.write((line + separator).encode("utf-8"))
    sys.stdout.buffer.flush()


def result(request_id: Any, value: dict[str, Any]) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "result": value})


def error(request_id: Any, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def update(update_payload: dict[str, Any]) -> None:
    send(
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"sessionId": SESSION, "update": update_payload},
        }
    )


def text(value: str, message_id: str = "msg_1") -> None:
    update(
        {
            "sessionUpdate": "agent_message_chunk",
            "messageId": message_id,
            "content": {"type": "text", "text": value},
        }
    )


def tool_call(tool_id: str = "call_1") -> None:
    update(
        {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_id,
            "title": "Read a file",
            "name": "read_file",
            "kind": "read",
            "status": "pending",
            "locations": [{"path": "/tmp/example.py", "line": 1}],
        }
    )


def prompt_result(request_id: Any, reason: str = "end_turn") -> None:
    result(request_id, {"stopReason": reason})


def main() -> int:
    pending_prompt: Any = None
    permission_pending = False
    while True:
        raw = sys.stdin.buffer.readline()
        if not raw:
            return 0
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            error(None, -32700, "invalid json")
            continue
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        request_id = message.get("id")
        if method == "initialize":
            result(
                request_id,
                {
                    "protocolVersion": 1,
                    "agentCapabilities": {
                        "loadSession": True,
                        "promptCapabilities": {
                            "image": True,
                            "embeddedContext": True,
                        },
                        "mcpCapabilities": {"http": True, "sse": False},
                        "sessionCapabilities": {
                            "resume": {},
                            "close": {},
                        },
                    },
                    "agentInfo": {"name": "fake-acp", "version": "1.0"},
                    "authMethods": [],
                },
            )
        elif method == "session/new":
            names = []
            servers = message.get("params", {}).get("mcpServers", [])
            if isinstance(servers, list):
                names = [str(row.get("name") or "") for row in servers if isinstance(row, dict)]
            global MCP_NAMES
            MCP_NAMES = names
            result(request_id, {"sessionId": SESSION})
        elif method == "session/load":
            text("loaded")
            result(request_id, {})
        elif method == "session/close":
            result(request_id, {})
        elif method == "session/prompt":
            pending_prompt = request_id
            if SCENARIO == "crash":
                return 3
            if SCENARIO == "cancel":
                text("working")
                continue
            if SCENARIO == "mcp":
                text("mcp:" + ",".join(MCP_NAMES))
                prompt_result(request_id)
                pending_prompt = None
                continue
            if SCENARIO == "permission":
                tool_call()
                permission_pending = True
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": PERMISSION_ID,
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": SESSION,
                            "toolCall": {
                                "toolCallId": "call_1",
                                "title": "Write a file",
                                "kind": "edit",
                                "status": "pending",
                            },
                            "options": [
                                {
                                    "optionId": "allow-once",
                                    "name": "Allow once",
                                    "kind": "allow_once",
                                },
                                {
                                    "optionId": "allow-always",
                                    "name": "Always allow",
                                    "kind": "allow_always",
                                },
                                {
                                    "optionId": "reject-once",
                                    "name": "Reject",
                                    "kind": "reject_once",
                                },
                            ],
                        },
                    }
                )
                continue
            text("hello from fake")
            tool_call()
            update(
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_1",
                    "status": "completed",
                    "content": [
                        {
                            "type": "content",
                            "content": {"type": "text", "text": "read complete"},
                        }
                    ],
                }
            )
            update(
                {
                    "sessionUpdate": "plan",
                    "entries": [
                        {"content": "Read the file", "priority": "high", "status": "completed"},
                        {"content": "Write the change", "priority": "medium", "status": "pending"},
                    ],
                }
            )
            update(
                {
                    "sessionUpdate": "usage_update",
                    "used": 10,
                    "size": 100,
                    "cost": {"amount": 0.001, "currency": "USD"},
                }
            )
            prompt_result(request_id)
            pending_prompt = None
        elif method == "session/cancel":
            if pending_prompt is not None:
                prompt_result(pending_prompt, "cancelled")
                pending_prompt = None
        elif message.get("id") == PERMISSION_ID and permission_pending:
            permission_pending = False
            outcome = message.get("result", {}).get("outcome", {})
            if outcome.get("outcome") == "selected":
                update(
                    {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": "call_1",
                        "status": "completed",
                        "content": [
                            {
                                "type": "content",
                                "content": {"type": "text", "text": "permission granted"},
                            }
                        ],
                    }
                )
                text("approved")
            else:
                text("cancelled")
            if pending_prompt is not None:
                prompt_result(pending_prompt)
                pending_prompt = None
        elif method is not None:
            error(request_id, -32601, f"unsupported {method}")


if __name__ == "__main__":
    raise SystemExit(main())
