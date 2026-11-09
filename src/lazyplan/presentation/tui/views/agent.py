"""Render an ACP transcript as markdown without importing Textual."""

from __future__ import annotations

from ....infrastructure.agents import PlanEntry, ToolCall


class AgentTranscript:
    """One conversation transcript with patched tool and plan blocks."""

    def __init__(self) -> None:
        self.blocks: list[str] = []
        self.kinds: list[str] = []
        self._tools: dict[str, ToolCall] = {}
        self._tool_blocks: dict[str, int] = {}
        self._plan_block: int | None = None

    def markdown(self) -> str:
        """The transcript as markdown."""
        return "\n\n".join(block for block in self.blocks if block)

    def add_user(self, text: str) -> None:
        self._append(f"**You**\n\n{text}", "user")

    def add_text(self, text: str) -> None:
        if text and self.kinds and self.kinds[-1] == "agent":
            self.blocks[-1] += text
        elif text:
            self._append(f"**Agent**\n\n{text}", "agent")

    def add_thought(self, text: str) -> None:
        self._append(f"_{text}_", "thought")

    def add_tool(self, tool: ToolCall, raw: dict) -> None:
        previous = self._tools.get(tool.tool_call_id)
        if previous is not None:
            tool = previous.merged(raw)
        elif raw:
            fresh = ToolCall.from_update(raw)
            tool = ToolCall(
                tool_call_id=tool.tool_call_id or fresh.tool_call_id,
                title=tool.title or fresh.title,
                name=tool.name or fresh.name,
                kind=tool.kind if tool.kind != "other" else fresh.kind,
                status=tool.status,
                content=tool.content or fresh.content,
                locations=tool.locations or fresh.locations,
                raw_input=tool.raw_input if tool.raw_input is not None else fresh.raw_input,
                raw_output=(tool.raw_output if tool.raw_output is not None else fresh.raw_output),
            )
        self._tools[tool.tool_call_id] = tool
        card = self._tool_card(tool)
        index = self._tool_blocks.get(tool.tool_call_id)
        if index is None:
            self._tool_blocks[tool.tool_call_id] = self._append(card, "tool")
        else:
            self.blocks[index] = card

    def add_plan(self, entries: tuple[PlanEntry, ...]) -> None:
        rows = "\n".join(f"> {entry.status} · {entry.content}" for entry in entries)
        block = f"**Plan**\n\n{rows}"
        if self._plan_block is None:
            self._plan_block = self._append(block, "plan")
        else:
            self.blocks[self._plan_block] = block

    def add_notice(self, title: str) -> None:
        self._append(f"> {title}", "notice")

    def add_permission(self, tool: ToolCall) -> None:
        name = tool.title or tool.name or "tool"
        self._append(f"> **Permission requested**\n> {name}", "permission")

    def add_exit(self) -> None:
        self._append("_agent exited_", "exit")

    def add_error(self, message: str) -> None:
        self._append(f"**Error**\n\n{message}", "error")

    def add_unknown(self, name: str) -> None:
        self._append(f"> unknown agent update: {name}", "unknown")

    def _append(self, text: str, kind: str) -> int:
        self.blocks.append(text)
        self.kinds.append(kind)
        return len(self.blocks) - 1

    @staticmethod
    def _tool_card(tool: ToolCall) -> str:
        lines = [f"**{tool.title or tool.name or 'tool'}** `{tool.kind}` · {tool.status}"]
        for item in tool.content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "diff":
                path = item.get("path") or "file"
                new_text = str(item.get("newText") or "").strip()
                lines.append(f"`{path}`")
                if new_text:
                    lines.append(f"```\n{new_text[:1200]}\n```")
            elif item.get("type") == "content":
                inner = item.get("content")
                if isinstance(inner, dict) and inner.get("type") == "text":
                    lines.append(str(inner.get("text") or "")[:1200])
        return "\n".join(line for line in lines if line)
