"""Startup health modal: when it opens and what it says."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.infrastructure.integrations import IntegrationItem
from lazyplan.presentation.setup.health import (
    ERROR,
    WARNING,
    HealthFinding,
    HealthReport,
)
from lazyplan.presentation.setup.integrations import ReviewResult

try:
    from textual.widgets import Label, Static

    from lazyplan.presentation.tui import create_app, launch
    from lazyplan.presentation.tui.launch import Restart
    from lazyplan.presentation.tui.screens import HealthScreen, TextScreen
except ImportError:  # pragma: no cover - textual not installed
    create_app = HealthScreen = None  # type: ignore[assignment]

HOOK = IntegrationItem(
    id="hook:claude:stop", kind="hook", label="Claude Code stop", fingerprint="f", host="claude"
)
HOOKS = HealthFinding(
    id="hook:claude",
    label="Claude Code hooks",
    capability="Claude Code sessions aren't tracked.",
    host="claude",
    items=(HOOK,),
)
GIT = HealthFinding(
    id="tool:git",
    label="git on PATH",
    capability="Commit links don't work.",
    fix="Install Git.",
)
GH = HealthFinding(
    id="tool:gh",
    label="GitHub CLI",
    capability="PR status can't refresh.",
    severity=WARNING,
    fix="Install gh.",
)


class FakeSession:
    def __init__(self, report: HealthReport, pending=()) -> None:
        self._report = report
        self.pending = pending
        self.installed: list[tuple[HealthFinding, ...]] = []
        self.decided: list[tuple[tuple[HealthFinding, ...], str]] = []

    def report(self) -> HealthReport:
        return self._report

    def install(self, findings: tuple[HealthFinding, ...]) -> ReviewResult:
        self.installed.append(findings)
        return ReviewResult(decision="install", pending=self.pending)

    def decide(self, findings: tuple[HealthFinding, ...], decision: str) -> None:
        self.decided.append((findings, decision))


@unittest.skipUnless(create_app is not None, "textual not installed")
class HealthScreenTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = os.path.join(self.tmp.name, "health.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def app(self, report: HealthReport, pending=()):
        self.session = FakeSession(report, pending)
        return create_app(self.db, health_check=lambda: self.session)

    async def settle(self, pilot) -> None:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    async def test_open_errors_open_the_modal_with_each_capability(self) -> None:
        app = self.app(HealthReport(findings=(HOOKS, GIT, GH)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertIsInstance(app.screen, HealthScreen)
            body = str(app.screen.query_one("#health-body", Static).render())
            for finding in (HOOKS, GIT, GH):
                self.assertIn(finding.label, body)
                self.assertIn(finding.capability, body)
            self.assertIn("Install Git.", body)
            self.assertIn("lazyplan can do less", body)

    async def test_not_now_closes_the_modal_and_defers(self) -> None:
        app = self.app(HealthReport(findings=(GIT,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, HealthScreen)
            self.assertEqual(len(app.screen_stack), 1)
        self.assertEqual(self.session.decided, [((GIT,), "deferred")])

    async def test_never_ask_remembers_never(self) -> None:
        app = self.app(HealthReport(findings=(HOOKS, GIT)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            await pilot.click("#health-never")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
        self.assertEqual(self.session.decided, [((HOOKS, GIT), "never")])
        self.assertEqual(self.session.installed, [])

    async def test_the_chip_counts_every_finding_including_hidden_ones(self) -> None:
        hidden = HealthFinding(**{**GIT.__dict__, "decision": "never"})
        app = self.app(HealthReport(findings=(hidden, GH)))
        async with app.run_test(size=(140, 40)) as pilot:
            await self.settle(pilot)
            hints = str(app.query_one("#hints", Label).render())
            self.assertIn("health", hints)
            self.assertIn("2 issues", hints)

    async def test_the_palette_review_lists_hidden_findings_and_only_closes(self) -> None:
        hidden = HealthFinding(**{**GIT.__dict__, "decision": "never"})
        app = self.app(HealthReport(findings=(hidden,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            app.action_health_prompt()
            await pilot.pause()
            self.assertIsInstance(app.screen, HealthScreen)
            body = str(app.screen.query_one("#health-body", Static).render())
            self.assertIn("(never ask)", body)
            self.assertFalse(app.screen.query("#health-never"))
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
        self.assertEqual(self.session.decided, [])

    async def test_the_palette_says_so_when_nothing_is_missing(self) -> None:
        app = self.app(HealthReport())
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            app.action_health_prompt()
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
            hints = str(app.query_one("#hints", Label).render())
            self.assertNotIn("health", hints)

    async def test_install_and_restart_installs_fixable_findings_then_exits(self) -> None:
        app = self.app(HealthReport(findings=(HOOKS, GIT)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            body = str(app.screen.query_one("#health-body", Static).render())
            self.assertIn("Install & restart adds the missing skills and hooks", body)
            await pilot.click("#health-install")
            await pilot.pause()
        self.assertEqual(self.session.installed, [(HOOKS,)])
        self.assertEqual(app.return_value, Restart(("Claude Code",)))

    async def test_hosts_the_installer_skipped_are_not_named(self) -> None:
        app = self.app(HealthReport(findings=(HOOKS,)), pending=(HOOK,))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            await pilot.click("#health-install")
            await pilot.pause()
        self.assertEqual(app.return_value, Restart(()))

    async def test_nothing_fixable_offers_no_install(self) -> None:
        app = self.app(HealthReport(findings=(GIT,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertFalse(app.screen.query("#health-install"))
            await pilot.click("#health-later")
            await pilot.pause()
            self.assertEqual(len(app.screen_stack), 1)
        self.assertEqual(self.session.installed, [])

    async def test_a_clean_report_stays_quiet(self) -> None:
        app = self.app(HealthReport())
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_warnings_alone_do_not_open_the_modal(self) -> None:
        app = self.app(HealthReport(findings=(GH,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_never_decisions_do_not_open_the_modal(self) -> None:
        hidden = HealthFinding(**{**GIT.__dict__, "decision": "never"})
        app = self.app(HealthReport(findings=(hidden,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)

    async def test_no_check_means_no_modal(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)
            self.assertIsNone(app.health_controller.report)

    async def test_a_failing_check_never_breaks_the_tui(self) -> None:
        def broken() -> HealthReport:
            raise RuntimeError("boom")

        app = create_app(self.db, health_check=broken)
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            self.assertEqual(len(app.screen_stack), 1)


class SeverityTest(unittest.TestCase):
    def test_tool_findings_default_to_errors(self) -> None:
        self.assertEqual(GIT.severity, ERROR)


@unittest.skipUnless(create_app is not None, "textual not installed")
class RelaunchTest(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop(launch.RESTART_ENV, None)

    def test_windows_waits_on_a_child_that_knows_the_agents(self) -> None:
        with (
            mock.patch.object(launch.os, "name", "nt"),
            mock.patch.object(launch.sys, "argv", ["lpui", "ui"]),
            mock.patch.object(launch.subprocess, "call", return_value=7) as call,
        ):
            self.assertEqual(launch.relaunch(Restart(("Claude Code", "Gemini CLI"))), 7)
        argv = call.call_args.args[0]
        self.assertEqual(argv, [launch.sys.executable, "-m", "lazyplan", "ui"])
        env = call.call_args.kwargs["env"]
        self.assertEqual(env[launch.RESTART_ENV], "Claude Code,Gemini CLI")

    def test_posix_replaces_the_process(self) -> None:
        with (
            mock.patch.object(launch.os, "name", "posix"),
            mock.patch.object(launch.sys, "argv", ["lpui"]),
            mock.patch.object(launch.os, "execve") as execve,
        ):
            launch.relaunch(Restart(("Codex",)))
        executable, argv, env = execve.call_args.args
        self.assertEqual(argv, [launch.sys.executable, "-m", "lazyplan"])
        self.assertEqual(env[launch.RESTART_ENV], "Codex")

    def test_the_notice_names_each_agent_once_then_clears(self) -> None:
        os.environ[launch.RESTART_ENV] = "Claude Code,Gemini CLI"
        notice = launch.take_restart_notice()
        self.assertIn("Restart any Claude Code and Gemini CLI sessions", notice)
        self.assertEqual(launch.take_restart_notice(), "")

    def test_skills_only_names_agents_in_general(self) -> None:
        os.environ[launch.RESTART_ENV] = ""
        self.assertIn("Restart any agent sessions", launch.take_restart_notice())

    def test_a_normal_launch_has_no_notice(self) -> None:
        self.assertEqual(launch.take_restart_notice(), "")


@unittest.skipUnless(create_app is not None, "textual not installed")
class RestartNoticeTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_relaunch_opens_the_restart_notice(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            notice = launch.restart_notice(["Claude Code"])
            app = create_app(os.path.join(tmp, "n.db"), restart_notice=notice)
            async with app.run_test(size=(110, 40)) as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, TextScreen)
                self.assertEqual(app.screen.dialog_title, "RESTART YOUR AGENTS")
                self.assertIn("Claude Code sessions", app.screen.HELP)


if __name__ == "__main__":
    unittest.main()
