"""Startup health modal: when it opens and what it says."""

from __future__ import annotations

import os
import tempfile
import unittest

from lazyplan.infrastructure.integrations import IntegrationItem
from lazyplan.presentation.setup.health import (
    ERROR,
    WARNING,
    HealthFinding,
    HealthReport,
)

try:
    from textual.widgets import Static

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens import HealthScreen
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


@unittest.skipUnless(create_app is not None, "textual not installed")
class HealthScreenTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = os.path.join(self.tmp.name, "health.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def app(self, report: HealthReport):
        return create_app(self.db, health_check=lambda: report)

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

    async def test_not_now_closes_the_modal(self) -> None:
        app = self.app(HealthReport(findings=(GIT,)))
        async with app.run_test(size=(110, 40)) as pilot:
            await self.settle(pilot)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, HealthScreen)
            self.assertEqual(len(app.screen_stack), 1)

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


if __name__ == "__main__":
    unittest.main()
