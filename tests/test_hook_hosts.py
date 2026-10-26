"""Host-specific hook envelopes for all five supported agents."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import hook_hosts  # noqa: E402
from lazyplan.hooks import HookResult  # noqa: E402


class HostCase(unittest.TestCase):
    def test_context_uses_the_native_event_and_field(self):
        for host, native in (
            ("claude", "SessionStart"),
            ("gemini", "SessionStart"),
            ("codex", "SessionStart"),
        ):
            body = json.loads(hook_hosts.render(host, "session-start", HookResult("hello", True)))
            output = body["hookSpecificOutput"]
            self.assertEqual(output["hookEventName"], native)
            self.assertEqual(output["additionalContext"], "hello")

    def test_warning_uses_system_message(self):
        for host in ("claude", "gemini", "codex"):
            body = json.loads(hook_hosts.render(host, "stop", HookResult("warn")))
            self.assertEqual(body, {"systemMessage": "warn"})

    def test_cursor_uses_agent_message(self):
        body = json.loads(hook_hosts.render("cursor", "stop", HookResult("warn")))
        self.assertEqual(body, {"agentMessage": "warn"})

    def test_opencode_gets_plain_text(self):
        self.assertEqual(hook_hosts.render("opencode", "stop", HookResult("warn")), "warn")

    def test_silent_result_is_empty(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            self.assertEqual(hook_hosts.render(host, "stop", HookResult()), "")

    def test_event_names_cover_every_canonical_event(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            for event in ("session-start", "prompt-submit", "post-tool", "stop", "pre-compact"):
                self.assertTrue(hook_hosts.event_name(host, event))

    def test_shell_matchers_follow_each_host_tool_name(self):
        self.assertEqual(hook_hosts.matcher("claude", "PostToolUse"), "Bash|PowerShell")
        self.assertEqual(hook_hosts.matcher("codex", "PostToolUse"), "Bash")
        self.assertEqual(hook_hosts.matcher("gemini", "AfterTool"), "run_shell_command")
        self.assertEqual(hook_hosts.matcher("claude", "SessionStart"), "*")

    def test_claude_has_no_pre_compact_output(self):
        self.assertEqual(hook_hosts.render("claude", "pre-compact", HookResult("hi", True)), "")
        body = json.loads(hook_hosts.render("codex", "pre-compact", HookResult("hi", True)))
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PreCompact")

    def test_output_has_no_ansi(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            text = hook_hosts.render(host, "session-start", HookResult("hello", True))
            self.assertNotIn("\x1b", text)


if __name__ == "__main__":
    unittest.main()
