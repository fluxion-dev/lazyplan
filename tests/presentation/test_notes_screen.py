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
    from lazyplan.presentation.tui import create_app
    from lazyplan.presentation.tui.launch import launch_notes
    from lazyplan.presentation.tui.screens import ReleaseNotesScreen
except ImportError:  # pragma: no cover - textual not installed
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
        self.tmp = tempfile.TemporaryDirectory()
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
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                os.path.join(tmp, "notes.db"),
                startup_notes="## v0.38.0 — 2026-11-11\n\n- New notes.",
            )
            async with app.run_test(size=(110, 35)) as pilot:
                await pilot.pause()
                self.assertIsInstance(app.screen, ReleaseNotesScreen)

    async def test_key_opens_the_installed_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
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

    def test_registry_names_the_palette_entry_and_key(self) -> None:
        action = registry.by_id("app.notes")
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.key, "W")
        self.assertIn("release-notes", action.palette_ids)
        command = registry.by_command_id("release-notes")
        self.assertIsNotNone(command)
        assert command is not None
        self.assertEqual(command.handler, "release_notes")
        self.assertEqual(command.key, "W")


if __name__ == "__main__":
    unittest.main()
