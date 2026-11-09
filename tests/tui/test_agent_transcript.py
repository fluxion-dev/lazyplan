"""The workbench transcript view model."""

from __future__ import annotations

import unittest

from lazyplan.infrastructure.agents import PlanEntry, ToolCall

try:
    from lazyplan.presentation.tui.views.agent import AgentTranscript

    _TEXTUAL_OK = True
except ImportError:  # stdlib-only interpreter
    _TEXTUAL_OK = False


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class TestAgentTranscript(unittest.TestCase):
    def test_text_and_thought_blocks(self) -> None:
        transcript = AgentTranscript()
        transcript.add_user("hello")
        transcript.add_text("one ")
        transcript.add_text("two")
        transcript.add_thought("thinking")
        self.assertIn("**You**\n\nhello", transcript.markdown())
        self.assertIn("**Agent**\n\none two", transcript.markdown())
        self.assertIn("_thinking_", transcript.markdown())

    def test_tool_update_patches_the_same_card(self) -> None:
        transcript = AgentTranscript()
        transcript.add_tool(
            ToolCall("call_1", title="Read a file", kind="read", status="pending"), {}
        )
        transcript.add_tool(
            ToolCall("call_1", status="completed"),
            {"status": "completed", "content": [{"type": "content"}]},
        )
        self.assertEqual(transcript.markdown().count("Read a file"), 1)
        self.assertIn("completed", transcript.markdown())

    def test_plan_replaces_in_place(self) -> None:
        transcript = AgentTranscript()
        transcript.add_plan((PlanEntry("first", status="pending"),))
        transcript.add_plan((PlanEntry("second", status="completed"),))
        self.assertNotIn("first", transcript.markdown())
        self.assertIn("second", transcript.markdown())

    def test_tool_diff_and_notice_blocks(self) -> None:
        transcript = AgentTranscript()
        transcript.add_tool(
            ToolCall("call_1", title="Edit", kind="edit", status="completed"),
            {
                "content": [
                    {
                        "type": "diff",
                        "path": "src/app.py",
                        "newText": "print('hello')",
                    }
                ]
            },
        )
        transcript.add_notice("heads up")
        transcript.add_unknown("future_update")
        text = transcript.markdown()
        self.assertIn("src/app.py", text)
        self.assertIn("print('hello')", text)
        self.assertIn("heads up", text)
        self.assertIn("unknown agent update: future_update", text)


if __name__ == "__main__":
    unittest.main()
