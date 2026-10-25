"""Host-specific hook output shapes.

The canonical reminder is plain text; each host expects its own JSON
envelope. OpenCode receives the text directly from its plugin.
"""

from __future__ import annotations

import json

from .hooks import HookResult

EVENTS: dict[str, dict[str, str]] = {
    "claude": {
        "session-start": "SessionStart",
        "prompt-submit": "UserPromptSubmit",
        "post-tool": "PostToolUse",
        "stop": "Stop",
        "pre-compact": "PreCompact",
    },
    "gemini": {
        "session-start": "SessionStart",
        "prompt-submit": "BeforeAgent",
        "post-tool": "AfterTool",
        "stop": "AfterAgent",
        "pre-compact": "PreCompress",
    },
    "codex": {
        "session-start": "SessionStart",
        "prompt-submit": "UserPromptSubmit",
        "post-tool": "PostToolUse",
        "stop": "Stop",
        "pre-compact": "PreCompact",
    },
    "cursor": {
        "session-start": "sessionStart",
        "prompt-submit": "beforeSubmitPrompt",
        "post-tool": "postToolUse",
        "stop": "stop",
        "pre-compact": "preCompact",
    },
    "opencode": {
        "session-start": "session-start",
        "prompt-submit": "prompt-submit",
        "post-tool": "post-tool",
        "stop": "stop",
        "pre-compact": "pre-compact",
    },
}


MATCHERS = {"PostToolUse": "Bash", "AfterTool": "run_shell_command"}


def event_name(host: str, event: str) -> str:
    """Native event name for one host; canonical name when unknown."""
    return EVENTS.get(host, {}).get(event, event)


def payload(host: str, event: str, result: HookResult) -> dict:
    """JSON body a host expects, or an empty object when the hook is silent."""
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
        return {"agentMessage": result.text}
    return {}


def render(host: str, event: str, result: HookResult) -> str:
    """Stdout text for one host; OpenCode gets the raw reminder."""
    if host == "opencode":
        return result.text
    body = payload(host, event, result)
    return json.dumps(body, separators=(",", ":")) if body else ""
