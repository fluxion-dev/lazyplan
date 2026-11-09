"""Headless Agent Workbench tests."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Button, Input, TextArea

from lazyplan.infrastructure.agents import AgentEvent, AgentProfile, ToolCall
from lazyplan.presentation.shared import registry
from lazyplan.presentation.tui import create_app
from lazyplan.presentation.tui.screens.agent import AgentScreen
from lazyplan.store import Store

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


class TestAgentScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "agent.db")
        Store(self.db).add_plan("P")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_prompt_streams_a_tool_card(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile(), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#agent-prompt").text = "hello"
            await screen.action_send()
            await wait_for(lambda: "hello from fake" in screen.transcript)
            self.assertIn("hello from fake", screen.transcript)
            self.assertEqual(screen.transcript.count("Read a file"), 1)
            self.assertIn("read complete", screen.transcript)
            self.assertIn("Write the change", screen.transcript)
            self.assertIn("10/100 tokens", str(screen.query_one("#agent-status").render()))
            await screen.action_close()

    async def test_permission_modal_allows_the_tool(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile("permission"), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#agent-prompt").text = "write"
            sending = asyncio.create_task(screen.action_send())
            await wait_for(lambda: app.screen.__class__.__name__ == "AgentPermissionScreen")
            await pilot.pause()
            modal = app.screen
            labels = [str(button.label) for button in modal.query(Button)]
            self.assertIn("Allow once", labels)
            self.assertIn("Always allow", labels)
            self.assertIn("Reject", labels)
            modal.query_one("#perm-0", Button).press()
            await wait_for(lambda: "approved" in screen.transcript)
            await asyncio.wait_for(sending, 5.0)
            await screen.action_close()

    async def test_permission_modal_rejects_the_tool(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile("permission"), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#agent-prompt").text = "write"
            sending = asyncio.create_task(screen.action_send())
            await wait_for(lambda: app.screen.__class__.__name__ == "AgentPermissionScreen")
            await pilot.pause()
            app.screen.query_one("#perm-cancel", Button).press()
            await wait_for(lambda: "cancelled" in screen.transcript)
            await asyncio.wait_for(sending, 5.0)
            await screen.action_close()

    async def test_failed_tool_adds_a_notice(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile(), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            await screen._apply_event(
                AgentEvent(
                    kind="tool_update",
                    tool=ToolCall("call_1", title="Read a file", status="failed"),
                )
            )
            self.assertIn("Read a file failed", screen.transcript)
            await screen.action_close()

    async def test_unknown_update_renders_a_generic_line(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile(), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            await screen._apply_event(
                AgentEvent(kind="unknown", payload={"sessionUpdate": "future_update"})
            )
            self.assertIn("unknown agent update: future_update", screen.transcript)
            await screen.action_close()

    async def test_start_work_claims_and_links_the_run(self) -> None:
        store = Store(self.db)
        plan = store.list_plans()[0]
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(milestone.id, "T", "Commit: one.", actor="fixture")
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(
                profile(),
                ROOT,
                store=store,
                task_id=task.id,
                prompt="work on it",
            )
            app.push_screen(screen)
            await pilot.pause()
            await screen.action_send()
            await wait_for(lambda: "hello from fake" in screen.transcript)
            current = store.get_task(task.id)
            self.assertEqual(current.status.value, "doing")
            self.assertIsNotNone(store.get_claim(task.id))
            runs = store.list_agent_runs()
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["task_id"], task.id)
            self.assertIsNotNone(runs[0]["lazyplan_session_id"])
            head = str(screen.query_one("#agent-head").render())
            self.assertIn(f"T{task.id} T", head)
            await screen.action_close()

    async def test_finish_records_the_summary_and_handoff(self) -> None:
        store = Store(self.db)
        plan = store.list_plans()[0]
        milestone = store.add_milestone(plan.id, "M", actor="fixture")
        task = store.add_task(milestone.id, "T", "Commit: one.", actor="fixture")
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile(), ROOT, store=store, task_id=task.id, prompt="work")
            app.push_screen(screen)
            await pilot.pause()
            await screen.action_send()
            await wait_for(lambda: "hello from fake" in screen.transcript)
            screen.query_one("#agent-finish", Button).press()
            await wait_for(lambda: app.screen.__class__.__name__ == "AgentFinishScreen")
            await pilot.pause()
            app.screen.query_one("#finish-summary", TextArea).text = "did the work"
            app.screen.query_one("#finish-handoff", Input).value = "next: T2"
            app.screen.query_one("#finish-apply", Button).press()
            await wait_for(lambda: store.list_agent_runs() == [])
            run = store.list_agent_runs(status="all")[0]
            self.assertEqual(run["status"], "done")
            self.assertEqual(run["summary"], "did the work")
            self.assertEqual(run["handoff"], "next: T2")
            await screen.action_close()

    async def test_status_strip_tracks_the_run(self) -> None:
        app = create_app(self.db)
        async with app.run_test() as pilot:
            screen = AgentScreen(profile("cancel"), ROOT)
            app.push_screen(screen)
            await pilot.pause()
            screen.query_one("#agent-prompt").text = "work"
            sending = asyncio.create_task(screen.action_send())
            await wait_for(lambda: app.agent_status == "running")
            self.assertIn("running", str(app.query_one("#agent-strip").render()))
            await screen.action_cancel()
            await asyncio.wait_for(sending, 5.0)
            await wait_for(lambda: app.agent_status == "idle")
            self.assertIn("idle", str(app.query_one("#agent-strip").render()))
            await screen.action_close()
            self.assertIn("W workbench", str(app.query_one("#agent-strip").render()))

    async def test_w_opens_the_workbench(self) -> None:
        self.assertIsNotNone(registry.by_command_id("open-agent"))
        app = create_app(self.db)
        async with app.run_test() as pilot:
            app.action_open_agent()
            await pilot.pause()
            self.assertEqual(app.screen.__class__.__name__, "AgentScreen")
            screen = app.screen
            assert isinstance(screen, AgentScreen)
            await screen.action_close()
            self.assertIn("W workbench", str(app.query_one("#agent-strip").render()))


if __name__ == "__main__":
    unittest.main()
