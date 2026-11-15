"""The taskbar pins the running version to the right and names cached updates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from textual.content import Content

    from lazyplan.presentation.cli.parser import package_version
    from lazyplan.presentation.setup.health import HealthFinding, HealthReport
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.widgets.taskbar import (
        Taskbar,
        badge_markup,
        taskbar_markup,
        version_text,
    )
except ImportError as exc:  # pragma: no cover - textual not installed
    raise unittest.SkipTest(f"textual not installed: {exc}") from None


def plain(markup: str) -> str:
    return Content.from_markup(markup).plain


class VersionTextTest(unittest.TestCase):
    def test_running_version_is_prefixed_once(self) -> None:
        self.assertEqual(version_text("0.47.0"), "v0.47.0")
        self.assertEqual(version_text("v0.47.0"), "v0.47.0")

    def test_a_newer_release_adds_an_arrow(self) -> None:
        self.assertEqual(version_text("0.47.0", "0.48.0"), "v0.47.0 → v0.48.0")

    def test_equal_or_older_cache_keeps_the_running_version(self) -> None:
        self.assertEqual(version_text("0.47.0", "0.47.0"), "v0.47.0")
        self.assertEqual(version_text("0.47.0", "0.46.0"), "v0.47.0")
        self.assertEqual(version_text("0.47.0", "not-a-version"), "v0.47.0")

    def test_an_empty_running_version_renders_nothing(self) -> None:
        self.assertEqual(version_text(""), "")
        self.assertEqual(version_text("  "), "")

    def test_the_badge_is_a_clickable_update_action(self) -> None:
        self.assertIn("@click=app.action_update_prompt", badge_markup("v0.47.0"))


class TaskbarMarkupTest(unittest.TestCase):
    def test_the_line_fills_the_width_and_ends_with_the_badge(self) -> None:
        line = taskbar_markup(
            " ? help · c commands",
            running="0.47.0",
            latest="0.48.0",
            width=40,
        )
        text = plain(line)
        self.assertEqual(len(text), 40)
        self.assertTrue(text.endswith("v0.47.0 → v0.48.0"))
        self.assertIn("help", text)

    def test_health_sits_left_of_the_version(self) -> None:
        text = plain(
            taskbar_markup(
                " ? help",
                health=" · health 2 issues",
                running="0.47.0",
                width=60,
            )
        )
        self.assertLess(text.index("health"), text.index("v0.47.0"))

    def test_a_narrow_bar_keeps_the_version_and_drops_hints(self) -> None:
        text = plain(
            taskbar_markup(
                " ? help · c commands · / filter",
                running="0.47.0",
                width=24,
            )
        )
        self.assertTrue(text.endswith("v0.47.0"))
        self.assertNotIn("filter", text)
        self.assertLessEqual(len(text), 24)

    def test_no_version_keeps_the_hints_untouched(self) -> None:
        line = taskbar_markup(" ? help", running="", width=40)
        self.assertEqual(plain(line), " ? help")


@unittest.skipUnless(create_app is not None, "textual not installed")
class TaskbarPilotTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = str(Path(self.tmp.name) / "plans.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def bar_text(self, app: object, pilot: object) -> str:
        await pilot.pause()
        return str(app.query_one("#hints", Taskbar).render())

    async def test_the_main_bar_pins_the_running_version(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            text = await self.bar_text(app, pilot)
            self.assertTrue(text.endswith(f"v{package_version()}"))
            self.assertIn("help", text)
            self.assertLessEqual(len(text), 120)

    async def test_the_badge_survives_a_narrow_terminal(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=(80, 24)) as pilot:
            text = await self.bar_text(app, pilot)
            self.assertTrue(text.endswith(f"v{package_version()}"))

    async def test_a_cached_update_adds_the_arrow_to_the_bar(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.update_controller.latest = "99.0.0"
            app.health_controller.refresh_hints()
            await pilot.pause()
            text = str(app.query_one("#hints", Taskbar).render())
            self.assertIn("→ v99.0.0", text)

    async def test_the_health_chip_stays_left_of_the_version(self) -> None:
        app = create_app(self.db)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            finding = HealthFinding(id="tool:git", label="git", capability="Commit links fail.")
            app.health_controller.report = HealthReport(findings=(finding,))
            app.health_controller.refresh_hints()
            await pilot.pause()
            text = str(app.query_one("#hints", Taskbar).render())
            self.assertLess(text.index("health"), text.index("v"))
