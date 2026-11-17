"""The routing matrix: every notify path logs, and only two paths toast."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.core.entities import PlanRevision
from lazyplan.presentation.tui.controllers.notifications import CAPACITY
from lazyplan.services.revisions import DiffResult
from tests.support.paths import ROOT

try:
    from textual.app import App

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.screens.plan_diff import PlanDiffScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - textual not installed
    _TEXTUAL_OK = False

TUI = ROOT / "src" / "lazyplan" / "presentation" / "tui"
SEVERITIES = ("information", "warning", "error")

REVISION = PlanRevision(
    id=1,
    plan_id=1,
    revision=1,
    approved_at=0.0,
    digest="b" * 64,
    snapshot="{}",
)
EMPTY_DIFF = DiffResult(
    plan_id=1,
    from_revision=REVISION,
    to_revision=None,
    entries=(),
    summary={"add": 0, "remove": 0, "change": 0, "move": 0, "total": 0},
)

NO_UPDATE = mock.patch.dict(os.environ, {"LAZYPLAN_NO_UPDATE_CHECK": "1"})


@unittest.skipUnless(_TEXTUAL_OK, "textual not installed")
class NotificationMatrixTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_every_severity_logs_and_only_warnings_and_errors_badge(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                for severity in SEVERITIES:
                    app.notify(f"{severity} message", severity=severity, source="matrix")
                await pilot.pause()
                entries = app.notification_log.snapshot()
                self.assertEqual([entry.severity for entry in entries], list(SEVERITIES))
                self.assertEqual([entry.source for entry in entries], ["matrix"] * 3)
                self.assertEqual(app.notification_log.unread, 2)

    async def test_no_ordinary_severity_reaches_textual(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                with mock.patch.object(App, "notify") as toast:
                    for severity in SEVERITIES:
                        app.notify(f"{severity} message", severity=severity)
                toast.assert_not_called()
                await pilot.pause()
                self.assertEqual(len(app.notification_log), 3)

    async def test_the_app_log_stays_capped(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                for index in range(CAPACITY + 5):
                    app.notify(f"m{index}")
                await pilot.pause()
                entries = app.notification_log.snapshot()
                self.assertEqual(len(entries), CAPACITY)
                self.assertEqual(entries[-1].message, f"m{CAPACITY + 4}")
                self.assertEqual(entries[0].message, "m5")

    async def test_a_screen_notification_names_its_screen(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(PlanDiffScreen(EMPTY_DIFF))
                await pilot.pause()
                app.notify("drift")
                await pilot.pause()
                self.assertEqual(app.notification_log.snapshot()[-1].source, "plan-diff")

    async def test_clearing_the_log_drops_the_badge(self) -> None:
        with NO_UPDATE:
            app = create_app(self.db)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.notify("broke", severity="error")
                await pilot.pause()
                app.notification_log.clear()
                app.refresh_taskbar()
                await pilot.pause()
                self.assertEqual(app.notification_log.snapshot(), ())
                self.assertEqual(app.notification_log.unread, 0)


class ToastExceptionTest(unittest.TestCase):
    def test_only_the_notification_path_toasts(self) -> None:
        calls: list[str] = []
        for path in sorted(TUI.rglob("*.py")):
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("def notify_toast(") or not stripped.startswith(
                    ("self.notify_toast(", "app.notify_toast(", "self.app.notify_toast(")
                ):
                    continue
                calls.append(f"{path.relative_to(TUI).as_posix()}")
        self.assertEqual(sorted(calls), ["app.py", "controllers/updates.py"])

    def test_one_module_owns_the_toast(self) -> None:
        source = (TUI / "notifications.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("super().notify("), 1)

    def test_no_direct_textual_notify_survives_elsewhere(self) -> None:
        offenders = []
        for path in sorted(TUI.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "super().notify(" in text and path.name != "notifications.py":
                offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
