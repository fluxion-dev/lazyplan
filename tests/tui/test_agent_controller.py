"""Headless tests for the TUI agent controller."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

from lazyplan.infrastructure.agents import AgentEvent, AgentProfile
from lazyplan.presentation.tui.controllers.agent import AgentController
from lazyplan.services.agents import lazyplan_mcp_server

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "tests" / "support" / "fake_acp.py"


def profile(scenario: str = "text") -> AgentProfile:
    return AgentProfile(
        "fake",
        "Fake",
        (sys.executable, str(FAKE)),
        {"FAKE_ACP_SCENARIO": scenario, "PYTHONIOENCODING": "utf-8"},
    )


async def wait_for(predicate) -> None:
    for _ in range(500):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not met")


class TestMcpConfig(unittest.TestCase):
    def test_server_command_uses_the_same_database(self) -> None:
        server = lazyplan_mcp_server("/tmp/agent.db")
        self.assertEqual(server["name"], "lazyplan")
        self.assertEqual(server["args"][:3], ["-m", "lazyplan", "--db"])
        self.assertIn("/tmp/agent.db", server["args"])
        self.assertEqual(server["args"][-1], "mcp")


class TestAgentController(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.events: list[AgentEvent] = []
        self.statuses: list[tuple[str, str]] = []

    def make(self, scenario: str = "text") -> AgentController:
        return AgentController(
            profile(scenario),
            ROOT,
            on_event=self.events.append,
            on_status=lambda status, detail: self.statuses.append((status, detail)),
        )

    async def test_start_prompt_and_close(self) -> None:
        controller = self.make()
        await controller.start()
        result = await controller.prompt("hello")
        await wait_for(lambda: any(event.kind == "tool_call" for event in self.events))
        await controller.close()
        self.assertEqual(result["stopReason"], "end_turn")
        self.assertTrue(any(event.kind == "text" for event in self.events))
        self.assertEqual(self.statuses[-1][0], "closed")

    async def test_permission_pauses_and_resumes(self) -> None:
        controller = self.make("permission")
        await controller.start()
        prompting = asyncio.create_task(controller.prompt("write"))
        await wait_for(lambda: any(event.kind == "permission" for event in self.events))
        permission = next(event.permission for event in self.events if event.kind == "permission")
        assert permission is not None
        self.assertEqual(controller.status, "waiting")
        await controller.reply_permission(permission.request_id, "allow-once")
        result = await asyncio.wait_for(prompting, 5.0)
        await controller.close()
        self.assertEqual(result["stopReason"], "end_turn")
        self.assertEqual(controller.status, "closed")

    async def test_cancel_returns_to_idle(self) -> None:
        controller = self.make("cancel")
        await controller.start()
        prompting = asyncio.create_task(controller.prompt("work"))
        await wait_for(lambda: any(event.kind == "text" for event in self.events))
        await controller.cancel()
        result = await asyncio.wait_for(prompting, 5.0)
        self.assertEqual(result["stopReason"], "cancelled")
        await wait_for(lambda: controller.status == "idle")
        await controller.close()

    async def test_second_prompt_is_rejected(self) -> None:
        controller = self.make("cancel")
        await controller.start()
        first = asyncio.create_task(controller.prompt("one"))
        await wait_for(lambda: controller.status == "running")
        with self.assertRaises(RuntimeError):
            await controller.prompt("two")
        await controller.cancel()
        await asyncio.wait_for(first, 5.0)
        await controller.close()

    async def test_mcp_server_is_forwarded(self) -> None:
        controller = AgentController(
            profile("mcp"),
            ROOT,
            on_event=self.events.append,
            on_status=lambda status, detail: self.statuses.append((status, detail)),
            mcp_servers=(lazyplan_mcp_server("/tmp/agent.db"),),
        )
        await controller.start()
        await controller.prompt("hello")
        await wait_for(lambda: any(event.text.startswith("mcp:") for event in self.events))
        text = next(event.text for event in self.events if event.text.startswith("mcp:"))
        self.assertEqual(text, "mcp:lazyplan")
        await controller.close()

    async def test_missing_command_reports_error(self) -> None:
        controller = AgentController(
            AgentProfile("missing", "Missing", (os.devnull,)),
            ROOT,
            on_event=self.events.append,
            on_status=lambda status, detail: self.statuses.append((status, detail)),
        )
        with self.assertRaises(OSError):
            await controller.start()
        self.assertEqual(controller.status, "error")


if __name__ == "__main__":
    unittest.main()
