"""Host-specific hook envelopes for all five supported agents."""

import json
import unittest

from lazyplan.infrastructure import hook_hosts
from lazyplan.services.hooks import HookResult


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

    def test_cursor_session_start_uses_additional_context(self):
        body = json.loads(hook_hosts.render("cursor", "session-start", HookResult("hi", True)))
        self.assertEqual(body, {"additional_context": "hi"})

    def test_cursor_post_tool_uses_additional_context(self):
        body = json.loads(hook_hosts.render("cursor", "post-tool", HookResult("hi")))
        self.assertEqual(body, {"additional_context": "hi"})

    def test_cursor_prompt_submit_has_no_context_field(self):
        body = json.loads(hook_hosts.render("cursor", "prompt-submit", HookResult("hi", True)))
        self.assertEqual(body, {"continue": True})
        self.assertNotIn("agentMessage", body)

    def test_opencode_gets_plain_text(self):
        self.assertEqual(hook_hosts.render("opencode", "stop", HookResult("warn")), "warn")

    def test_silent_result_is_empty(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            self.assertEqual(hook_hosts.render(host, "stop", HookResult()), "")

    def test_event_names_cover_every_canonical_event(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            for event in (
                "session-start",
                "prompt-submit",
                "pre-tool",
                "post-tool",
                "stop",
                "session-end",
                "pre-compact",
            ):
                self.assertTrue(hook_hosts.event_name(host, event))

    def test_shell_matchers_follow_each_host_tool_name(self):
        self.assertEqual(hook_hosts.matcher("claude", "PostToolUse"), "Bash|PowerShell|Edit|Write")
        self.assertEqual(hook_hosts.matcher("codex", "PostToolUse"), "Bash|apply_patch|Edit|Write")
        self.assertEqual(
            hook_hosts.matcher("gemini", "AfterTool"), "run_shell_command|replace|write_file"
        )
        self.assertEqual(hook_hosts.matcher("claude", "SessionStart"), "*")

    def test_claude_pre_compact_is_raw_summary_guidance(self):
        self.assertEqual(
            hook_hosts.render("claude", "pre-compact", HookResult("keep the task", True)),
            "keep the task",
        )
        body = json.loads(hook_hosts.render("codex", "pre-compact", HookResult("hi", True)))
        self.assertEqual(body["hookSpecificOutput"]["hookEventName"], "PreCompact")

    def test_claude_denies_a_tool_before_it_runs(self):
        body = json.loads(hook_hosts.render("claude", "pre-tool", HookResult(block="no task")))
        output = body["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertEqual(output["permissionDecision"], "deny")
        self.assertEqual(output["permissionDecisionReason"], "no task")

    def test_claude_blocks_a_stop_once(self):
        body = json.loads(hook_hosts.render("claude", "stop", HookResult(block="link it")))
        self.assertEqual(body, {"decision": "block", "reason": "link it"})

    def test_codex_shapes_match_claude_for_tool_and_stop(self):
        deny = json.loads(hook_hosts.render("codex", "pre-tool", HookResult(block="no task")))
        self.assertEqual(deny["hookSpecificOutput"]["permissionDecision"], "deny")
        stop = json.loads(hook_hosts.render("codex", "stop", HookResult(block="link it")))
        self.assertEqual(stop, {"decision": "block", "reason": "link it"})

    def test_gemini_uses_decision_and_reason(self):
        for event in ("pre-tool", "stop"):
            body = json.loads(hook_hosts.render("gemini", event, HookResult(block="no task")))
            self.assertEqual(body, {"decision": "deny", "reason": "no task"})

    def test_cursor_denies_a_shell_command(self):
        body = json.loads(hook_hosts.render("cursor", "pre-tool", HookResult(block="no task")))
        self.assertEqual(body["permission"], "deny")
        self.assertEqual(body["agent_message"], "no task")
        self.assertTrue(body["continue"])

    def test_cursor_continues_after_a_stop_block(self):
        body = json.loads(hook_hosts.render("cursor", "stop", HookResult(block="link it")))
        self.assertEqual(body, {"followup_message": "link it"})

    def test_opencode_gets_the_block_reason_as_text(self):
        self.assertEqual(
            hook_hosts.render("opencode", "pre-tool", HookResult(block="no task")), "no task"
        )

    def test_block_reason_survives_capping(self):
        result = HookResult("", False, "x" * 5000).capped()
        self.assertEqual(len(result.block), 2000)

    def test_output_has_no_ansi(self):
        for host in ("claude", "gemini", "codex", "cursor", "opencode"):
            text = hook_hosts.render(host, "session-start", HookResult("hello", True))
            self.assertNotIn("\x1b", text)


if __name__ == "__main__":
    unittest.main()
