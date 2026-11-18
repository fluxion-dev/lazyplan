"""Release notes in the TUI: launch notice, key, and palette entry."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from lazyplan.presentation.shared import registry
from lazyplan.services import notes
from tests.support.home import sandbox_home

try:
    from textual.widgets import Markdown

    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.launch import launch_notes
    from lazyplan.presentation.tui.screens import ReleaseNotesScreen
except ImportError:  # pragma: no cover - textual not installed
    Markdown = None  # type: ignore[assignment,misc]
    create_app = launch_notes = ReleaseNotesScreen = None  # type: ignore[assignment]

SAMPLE = """# Changelog

## v0.38.0 — 2026-11-11

### Added

- New release notes.

## v0.37.0 — 2026-11-10

### Changed

- Mid release.
"""


@unittest.skipUnless(launch_notes is not None, "textual not installed")
class TestLaunchNotes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        sandbox_home(self, self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_first_launch_is_quiet_and_an_upgrade_shows_once(self) -> None:
        with (
            mock.patch("lazyplan.presentation.tui.launch.package_version", return_value="0.38.0"),
            mock.patch.object(notes, "bundled_text", return_value=SAMPLE),
        ):
            self.assertEqual(launch_notes(), "")
            notes.write_seen("0.36.0")
            first = launch_notes()
            second = launch_notes()
        self.assertIn("## v0.37.0", first)
        self.assertIn("## v0.38.0", first)
        self.assertEqual(second, "")


@unittest.skipUnless(create_app is not None, "textual not installed")
class TestReleaseNotesScreen(unittest.IsolatedAsyncioTestCase):
    async def test_startup_notes_open_the_read_only_screen(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(
                os.path.join(tmp, "notes.db"),
                startup_notes="## v0.38.0 — 2026-11-11\n\n- New notes.",
            )
            async with app.run_test(size=(110, 35)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ReleaseNotesScreen):
                        break
                self.assertIsInstance(app.screen, ReleaseNotesScreen)
                await pilot.press("escape")
                await pilot.pause()
                self.assertNotIsInstance(app.screen, ReleaseNotesScreen)
                self.assertEqual(len(app.screen_stack), 1)

    async def test_notes_render_as_markdown(self) -> None:
        text = (
            "## v0.49.0 — 2026-11-17\n\n### Added\n\n"
            "- **Bold** and `code` with [a link](https://example.com).\n"
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "notes.db"), startup_notes=text)
            async with app.run_test(size=(110, 35)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ReleaseNotesScreen):
                        break
                self.assertIsInstance(app.screen, ReleaseNotesScreen)
                await pilot.pause()
                markdown = app.screen.query_one("#notes-body", Markdown)
                self.assertEqual(markdown.source, text)
                children = [type(child).__name__ for child in markdown.children]
                self.assertIn("MarkdownH2", children)
                self.assertIn("MarkdownH3", children)
                self.assertIn("MarkdownBulletList", children)

    async def test_a_link_opens_in_the_browser(self) -> None:
        text = "## v0.49.0 — 2026-11-17\n\n[release page](https://example.com/notes)\n"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "notes.db"), startup_notes=text)
            async with app.run_test(size=(110, 35)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ReleaseNotesScreen):
                        break
                markdown = app.screen.query_one("#notes-body", Markdown)
                with mock.patch.object(app, "open_url") as opened:
                    markdown.post_message(
                        Markdown.LinkClicked(markdown, "https://example.com/notes")
                    )
                    await pilot.pause()
                opened.assert_called_once_with("https://example.com/notes")

    async def test_a_failed_link_open_is_a_warning_not_a_crash(self) -> None:
        text = "## v0.49.0 — 2026-11-17\n\n[release page](https://example.com/notes)\n"
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "notes.db"), startup_notes=text)
            async with app.run_test(size=(110, 35)) as pilot:
                for _ in range(40):
                    await pilot.pause(0.05)
                    if isinstance(app.screen, ReleaseNotesScreen):
                        break
                markdown = app.screen.query_one("#notes-body", Markdown)
                with mock.patch.object(app, "open_url", side_effect=RuntimeError("no browser")):
                    markdown.post_message(
                        Markdown.LinkClicked(markdown, "https://example.com/notes")
                    )
                    await pilot.pause()
                messages = [entry.message for entry in app.notification_log.snapshot()]
                self.assertTrue(any("no browser" in message for message in messages), messages)
                self.assertIsInstance(app.screen, ReleaseNotesScreen)

    async def test_key_opens_the_installed_notes(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "notes.db"))
            with mock.patch.object(
                notes,
                "select_notes",
                return_value=((), "## v0.37.0 — 2026-11-10\n\n- Notes."),
            ):
                async with app.run_test(size=(110, 35)) as pilot:
                    await pilot.pause()
                    await pilot.press("W")
                    await pilot.pause()
                    self.assertIsInstance(app.screen, ReleaseNotesScreen)

    def test_palette_uses_the_same_handler_as_the_key(self) -> None:
        from lazyplan.presentation.tui.palette_handlers import palette_handlers

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            app = create_app(os.path.join(tmp, "notes.db"))
            self.assertEqual(
                palette_handlers(app)["release_notes"],
                app.action_release_notes,
            )

    def test_registry_names_the_palette_entry_and_key(self) -> None:
        action = registry.by_id("app.notes")
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.key, "W")
        self.assertIn("tui", action.surfaces)
        self.assertIn("release-notes", action.palette_ids)
        command = registry.by_command_id("release-notes")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.handler, "release_notes")
        self.assertEqual(command.key, "W")


if __name__ == "__main__":
    unittest.main()
