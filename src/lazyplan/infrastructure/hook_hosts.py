"""Host-specific hook output shapes.

The canonical reminder is plain text; each host expects its own JSON
envelope. OpenCode receives the text directly from its plugin. A host with
no native name for an event never gets that event: Claude Code rejects
context on PreCompact and re-runs SessionStart after compaction instead.
"""

from __future__ import annotations

import json

from ..core.entities import HookResult

EVENTS: dict[str, dict[str, str]] = {
    "claude": {
        "session-start": "SessionStart",
        "prompt-submit": "UserPromptSubmit",
        "pre-tool": "PreToolUse",
        "post-tool": "PostToolUse",
        "stop": "Stop",
        "session-end": "SessionEnd",
    },
    "gemini": {
        "session-start": "SessionStart",
        "prompt-submit": "BeforeAgent",
        "pre-tool": "BeforeTool",
        "post-tool": "AfterTool",
        "stop": "AfterAgent",
        "session-end": "SessionEnd",
        "pre-compact": "PreCompress",
    },
    "codex": {
        "session-start": "SessionStart",
        "prompt-submit": "UserPromptSubmit",
        "pre-tool": "PreToolUse",
        "post-tool": "PostToolUse",
        "stop": "Stop",
        "session-end": "SessionEnd",
        "pre-compact": "PreCompact",
    },
    "cursor": {
        "session-start": "sessionStart",
        "prompt-submit": "beforeSubmitPrompt",
        "pre-tool": "beforeShellExecution",
        "post-tool": "postToolUse",
        "stop": "stop",
        "session-end": "sessionEnd",
        "pre-compact": "preCompact",
    },
    "opencode": {
        "session-start": "session-start",
        "prompt-submit": "prompt-submit",
        "pre-tool": "pre-tool",
        "post-tool": "post-tool",
        "stop": "stop",
        "session-end": "session-end",
        "pre-compact": "pre-compact",
    },
}


MATCHERS: dict[str, dict[str, str]] = {
    "claude": {
        "PreToolUse": "Bash|PowerShell",
        "PostToolUse": "Bash|PowerShell|Edit|Write",
    },
    "codex": {
        "PreToolUse": "Bash",
        "PostToolUse": "Bash|apply_patch|Edit|Write",
    },
    "gemini": {
        "BeforeTool": "run_shell_command",
        "AfterTool": "run_shell_command|replace|write_file",
    },
    "cursor": {"beforeShellExecution": "*", "postToolUse": "Shell|Write"},
}


def matcher(host: str, native: str) -> str:
    """Tool matcher for one host event; every tool when the event has none."""
    return MATCHERS.get(host, {}).get(native, "*")


def event_name(host: str, event: str) -> str:
    """Native event name for one host; canonical name when unknown."""
    return EVENTS.get(host, {}).get(event, event)


def _block_payload(host: str, event: str, reason: str) -> dict:
    """Native deny or block envelope for one host event."""
    native = event_name(host, event)
    if host == "claude":
        if event == "pre-tool":
            return {
                "hookSpecificOutput": {
                    "hookEventName": native,
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        return {"decision": "block", "reason": reason}
    if host == "codex":
        if event == "pre-tool":
            return {
                "hookSpecificOutput": {
                    "hookEventName": native,
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        return {"decision": "block", "reason": reason}
    if host == "gemini":
        return {"decision": "deny", "reason": reason}
    if host == "cursor":
        if event == "pre-tool":
            return {
                "continue": True,
                "permission": "deny",
                "user_message": reason,
                "agent_message": reason,
            }
        return {"followup_message": reason}
    return {}


def payload(host: str, event: str, result: HookResult) -> dict:
    """JSON body a host expects, or an empty object when the hook is silent."""
    if event not in EVENTS.get(host, {}):
        return {}
    if result.block:
        return _block_payload(host, event, result.block)
    if not result.text:
        return {}
    if host in ("claude", "gemini", "codex"):
        if result.context:
            return {
                "hookSpecificOutput": {
                    "hookEventName": event_name(host, event),
                    "additionalContext": result.text,
                }
            }
        return {"systemMessage": result.text}
    if host == "cursor":
        if event == "session-start":
            return {"additional_context": result.text}
        return {"agentMessage": result.text}
    return {}


def render(host: str, event: str, result: HookResult) -> str:
    """Stdout text for one host; OpenCode gets the raw reminder or reason."""
    if host == "opencode":
        return result.block or result.text
    body = payload(host, event, result)
    return json.dumps(body, separators=(",", ":")) if body else ""
