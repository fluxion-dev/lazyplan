"""Typed Agent Client Protocol events used by the workbench and tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanEntry:
    """One step in the agent's execution plan."""

    content: str = ""
    priority: str = "medium"
    status: str = "pending"


@dataclass(frozen=True)
class Usage:
    """Context-window usage and optional cumulative cost."""

    used: int = 0
    size: int = 0
    amount: float | None = None
    currency: str = ""


@dataclass(frozen=True)
class PermissionOption:
    """One choice in an ACP permission request."""

    option_id: str
    name: str
    kind: str


@dataclass(frozen=True)
class ToolCall:
    """One agent tool call, patched as ACP updates arrive."""

    tool_call_id: str
    title: str = ""
    name: str = ""
    kind: str = "other"
    status: str = "pending"
    content: tuple[dict[str, Any], ...] = ()
    locations: tuple[dict[str, Any], ...] = ()
    raw_input: Any = None
    raw_output: Any = None

    @classmethod
    def from_update(cls, update: dict[str, Any]) -> ToolCall:
        """Build the first version of a tool call from an ACP update."""
        return cls(
            tool_call_id=str(update.get("toolCallId") or ""),
            title=str(update.get("title") or ""),
            name=str(update.get("name") or ""),
            kind=str(update.get("kind") or "other"),
            status=str(update.get("status") or "pending"),
            content=_content(update.get("content")),
            locations=_content(update.get("locations")),
            raw_input=update.get("rawInput"),
            raw_output=update.get("rawOutput"),
        )

    def merged(self, update: dict[str, Any]) -> ToolCall:
        """Return this tool call with the fields present in one update replaced."""
        return ToolCall(
            tool_call_id=str(update.get("toolCallId") or self.tool_call_id),
            title=_text(update, "title", self.title),
            name=_text(update, "name", self.name),
            kind=_text(update, "kind", self.kind),
            status=_text(update, "status", self.status),
            content=_content(update.get("content")) if "content" in update else self.content,
            locations=(
                _content(update.get("locations")) if "locations" in update else self.locations
            ),
            raw_input=update.get("rawInput", self.raw_input),
            raw_output=update.get("rawOutput", self.raw_output),
        )


@dataclass(frozen=True)
class PermissionRequest:
    """An ACP request from the agent that needs a user decision."""

    request_id: int | str
    session_id: str
    tool: ToolCall
    options: tuple[PermissionOption, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentEvent:
    """One normalized event from an agent process."""

    kind: str
    session_id: str = ""
    text: str = ""
    message_id: str = ""
    tool: ToolCall | None = None
    plan: tuple[PlanEntry, ...] = ()
    usage: Usage | None = None
    permission: PermissionRequest | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def _text(update: dict[str, Any], key: str, default: str) -> str:
    value = update.get(key)
    return default if value is None else str(value)


def _content(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _text_block(content: Any) -> str:
    if not isinstance(content, dict):
        return ""
    if content.get("type") != "text":
        return ""
    return str(content.get("text") or "")


def _text_update(session_id: str, update: dict[str, Any], kind: str) -> AgentEvent:
    return AgentEvent(
        kind=kind,
        session_id=session_id,
        text=_text_block(update.get("content")),
        message_id=str(update.get("messageId") or ""),
        payload=update,
    )


def _tool_event(session_id: str, update: dict[str, Any]) -> AgentEvent:
    return AgentEvent(
        kind="tool_call",
        session_id=session_id,
        tool=ToolCall.from_update(update),
        payload=update,
    )


def _tool_update_event(session_id: str, update: dict[str, Any]) -> AgentEvent:
    return AgentEvent(
        kind="tool_update",
        session_id=session_id,
        tool=ToolCall.from_update(update),
        payload=update,
    )


def _plan_event(session_id: str, update: dict[str, Any]) -> AgentEvent:
    entries = update.get("entries")
    rows: list[PlanEntry] = []
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            rows.append(
                PlanEntry(
                    content=str(entry.get("content") or ""),
                    priority=str(entry.get("priority") or "medium"),
                    status=str(entry.get("status") or "pending"),
                )
            )
    return AgentEvent(kind="plan", session_id=session_id, plan=tuple(rows), payload=update)


def _usage_event(session_id: str, update: dict[str, Any]) -> AgentEvent:
    cost = update.get("cost")
    amount: float | None = None
    currency = ""
    if isinstance(cost, dict):
        given = cost.get("amount")
        if isinstance(given, int | float):
            amount = float(given)
        currency = str(cost.get("currency") or "")
    used = update.get("used")
    size = update.get("size")
    return AgentEvent(
        kind="usage",
        session_id=session_id,
        usage=Usage(
            used=used if isinstance(used, int) else 0,
            size=size if isinstance(size, int) else 0,
            amount=amount,
            currency=currency,
        ),
        payload=update,
    )


def _simple_event(kind: str) -> Callable[[str, dict[str, Any]], AgentEvent]:
    def build(session_id: str, update: dict[str, Any]) -> AgentEvent:
        return AgentEvent(kind=kind, session_id=session_id, payload=update)

    return build


def map_session_update(session_id: str, update: dict[str, Any]) -> AgentEvent:
    """Normalize one `session/update` payload."""
    kind = str(update.get("sessionUpdate") or "unknown")
    handler = _UPDATE_HANDLERS.get(kind)
    if handler is None:
        return AgentEvent(kind="unknown", session_id=session_id, payload=update)
    return handler(session_id, update)


_UPDATE_HANDLERS: dict[str, Callable[[str, dict[str, Any]], AgentEvent]] = {
    "agent_message_chunk": lambda session_id, update: _text_update(session_id, update, "text"),
    "agent_thought_chunk": lambda session_id, update: _text_update(session_id, update, "thought"),
    "user_message_chunk": lambda session_id, update: _text_update(session_id, update, "user"),
    "tool_call": _tool_event,
    "tool_call_update": _tool_update_event,
    "plan": _plan_event,
    "usage_update": _usage_event,
    "session_info_update": _simple_event("session_info"),
    "available_commands_update": _simple_event("commands"),
    "current_mode_update": _simple_event("mode"),
    "config_option_update": _simple_event("config"),
    "notice": _simple_event("notice"),
    "compaction_update": _simple_event("compaction"),
    "compaction_summary_chunk": _simple_event("compaction"),
}


def map_server_request(request_id: int | str, method: str, params: dict[str, Any]) -> AgentEvent:
    """Normalize one agent-to-client request."""
    if method == "session/request_permission":
        tool = params.get("toolCall")
        options = params.get("options")
        rows: list[PermissionOption] = []
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                rows.append(
                    PermissionOption(
                        option_id=str(option.get("optionId") or ""),
                        name=str(option.get("name") or ""),
                        kind=str(option.get("kind") or "reject_once"),
                    )
                )
        return AgentEvent(
            kind="permission",
            session_id=str(params.get("sessionId") or ""),
            tool=ToolCall.from_update(tool if isinstance(tool, dict) else {}),
            permission=PermissionRequest(
                request_id=request_id,
                session_id=str(params.get("sessionId") or ""),
                tool=ToolCall.from_update(tool if isinstance(tool, dict) else {}),
                options=tuple(rows),
                raw=params,
            ),
            payload=params,
        )
    return AgentEvent(
        kind="request",
        payload={"method": method, "params": params},
    )
