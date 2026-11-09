"""ACP transport tests driven by the scripted fake agent."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from collections.abc import Callable
from pathlib import Path

from lazyplan.infrastructure.agents import (
    AcpClient,
    AcpError,
    AgentEvent,
    map_session_update,
)

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "tests" / "support" / "fake_acp.py"


def client(scenario: str = "text", *, crlf: bool = False) -> AcpClient:
    env = dict(os.environ)
    env["FAKE_ACP_SCENARIO"] = scenario
    env["PYTHONIOENCODING"] = "utf-8"
    if crlf:
        env["FAKE_ACP_CRLF"] = "1"
    return AcpClient([sys.executable, str(FAKE)], ROOT, env=env)


async def take(
    acp: AcpClient,
    done: Callable[[AgentEvent], bool],
    timeout: float = 5.0,
) -> list[AgentEvent]:
    """Collect events until *done* returns true."""
    seen: list[AgentEvent] = []

    async def run() -> None:
        async for event in acp.events():
            seen.append(event)
            if done(event):
                return

    await asyncio.wait_for(run(), timeout)
    return seen


class TestAcpClient(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_and_new_session(self) -> None:
        async with client() as acp:
            initialized = await acp.initialize()
            self.assertEqual(initialized["protocolVersion"], 1)
            self.assertTrue(acp.agent_capabilities["loadSession"])
            session_id = await acp.new_session()
            self.assertEqual(session_id, "sess_test")

    async def test_prompt_streams_text_and_a_tool_call(self) -> None:
        async with client() as acp:
            await acp.initialize()
            session_id = await acp.new_session()
            result = await acp.prompt(session_id, "hello")
            seen = await take(acp, lambda event: event.kind == "tool_call")

        self.assertEqual(result["stopReason"], "end_turn")
        self.assertTrue(any(event.kind == "text" and "hello" in event.text for event in seen))
        tool = next(event.tool for event in seen if event.tool is not None)
        self.assertEqual(tool.title, "Read a file")
        self.assertEqual(tool.kind, "read")

    async def test_permission_reply_unblocks_the_prompt(self) -> None:
        async with client("permission") as acp:
            await acp.initialize()
            session_id = await acp.new_session()
            prompting = asyncio.create_task(acp.prompt(session_id, "write"))
            seen = await take(acp, lambda event: event.kind == "permission")
            permission = seen[-1].permission
            assert permission is not None
            self.assertEqual(permission.options[0].kind, "allow_once")
            await acp.reply_permission(permission.request_id, "allow-once")
            result = await asyncio.wait_for(prompting, 5.0)

        self.assertEqual(result["stopReason"], "end_turn")

    async def test_cancel_stops_the_active_prompt(self) -> None:
        async with client("cancel") as acp:
            await acp.initialize()
            session_id = await acp.new_session()
            prompting = asyncio.create_task(acp.prompt(session_id, "work"))
            await take(acp, lambda event: event.kind == "text")
            await acp.cancel(session_id)
            result = await asyncio.wait_for(prompting, 5.0)

        self.assertEqual(result["stopReason"], "cancelled")

    async def test_process_exit_fails_the_pending_prompt(self) -> None:
        acp = client("crash")
        await acp.start()
        try:
            await acp.initialize()
            session_id = await acp.new_session()
            with self.assertRaises(AcpError):
                await acp.prompt(session_id, "work", timeout=5.0)
        finally:
            await acp.close()

    async def test_crlf_frames_are_accepted(self) -> None:
        async with client(crlf=True) as acp:
            await acp.initialize()
            session_id = await acp.new_session()
            result = await acp.prompt(session_id, "hello")
        self.assertEqual(result["stopReason"], "end_turn")

    async def test_close_is_idempotent(self) -> None:
        acp = client()
        await acp.start()
        await acp.initialize()
        await acp.close()
        await acp.close()
        self.assertFalse(acp.running)


class TestEventMapping(unittest.TestCase):
    def test_unknown_update_maps_to_a_generic_event(self) -> None:
        event = map_session_update("sess_test", {"sessionUpdate": "future_update"})
        self.assertEqual(event.kind, "unknown")
        self.assertEqual(event.session_id, "sess_test")

    def test_tool_update_patches_the_existing_call(self) -> None:
        first = map_session_update(
            "sess_test",
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_1",
                "title": "Read a file",
                "status": "pending",
            },
        )
        assert first.tool is not None
        second = map_session_update(
            "sess_test",
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "call_1",
                "status": "completed",
            },
        )
        assert second.tool is not None
        self.assertEqual(first.tool.merged(second.payload).status, "completed")
        self.assertEqual(first.tool.merged(second.payload).title, "Read a file")


if __name__ == "__main__":
    unittest.main()
