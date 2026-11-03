"""ExportScreen: defaults, browsing, overwrite protection, and inline errors."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.store import Store

try:
    from lazyplan.presentation import tui as tui_mod
except ImportError:  # stdlib-only interpreter: no textual
    tui_mod = None  # type: ignore[assignment]


@unittest.skipUnless(tui_mod is not None and tui_mod._TEXTUAL_OK, "textual not installed")
class TestExportScreen(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.downloads = self.root / "Downloads"
        self.downloads.mkdir()
        self.db = str(self.root / "t.db")
        store = Store(self.db)
        self.pid = store.add_plan("Website", "Marketing site", goal="Convert").id
        self.sid = store.add_milestone(self.pid, "Homepage", "Hero work").id
        self.tid = store.add_task(self.sid, "Design hero", "Hero section").id
        self.store = Store(self.db)
        self.app = tui_mod.create_app(self.db)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _screen(self):
        from lazyplan.presentation.tui.screens.export import ExportScreen

        return ExportScreen(
            self.store,
            self.pid,
            "Website",
            default_dir=self.downloads,
        )

    async def test_defaults_to_downloads_and_names_the_plan(self) -> None:
        from textual.widgets import DirectoryTree, Input, Label

        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen())
            await pilot.pause()
            screen = self.app.screen
            value = screen.query_one("#export-path", Input).value
            self.assertTrue(value.endswith(f"plan-P{self.pid}.md"))
            self.assertEqual(Path(value).parent.resolve(), self.downloads.resolve())
            tree = screen.query_one("#export-tree", DirectoryTree)
            self.assertEqual(Path(tree.path).resolve(), self.downloads.resolve())
            labels = " ".join(str(label.content) for label in screen.query(Label))
            self.assertIn("Website", labels)

    async def test_folder_selection_keeps_the_filename(self) -> None:
        from textual.widgets import Input

        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen())
            await pilot.pause()
            screen = self.app.screen
            sub = self.downloads / "nested"
            sub.mkdir()
            screen._set_folder(sub)
            value = Path(screen.query_one("#export-path", Input).value)
            self.assertEqual(value.parent.resolve(), sub.resolve())
            self.assertEqual(value.name, f"plan-P{self.pid}.md")

    async def test_real_directory_selection_updates_the_path(self) -> None:
        from textual.widgets import DirectoryTree, Input

        sub = self.downloads / "nested"
        sub.mkdir()
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen())
            await pilot.pause()
            screen = self.app.screen
            tree = screen.query_one("#export-tree", DirectoryTree)
            tree.root.expand()
            await pilot.pause()
            node = next(child for child in tree.root.children if "nested" in str(child.label))
            tree.select_node(node)
            await pilot.pause()
            value = Path(screen.query_one("#export-path", Input).value).expanduser()
            self.assertEqual(value.parent.resolve(), sub.resolve())

    async def test_missing_downloads_falls_back_to_the_current_directory(self) -> None:
        from textual.widgets import Input

        from lazyplan.presentation.tui.screens.export import ExportScreen

        home = self.root / "bare-home"
        home.mkdir()
        old_cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with mock.patch.dict(
                os.environ,
                {"HOME": str(home), "USERPROFILE": str(home)},
            ):
                screen = ExportScreen(self.store, self.pid, "Website")
        finally:
            os.chdir(old_cwd)
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(screen)
            await pilot.pause()
            value = Path(screen.query_one("#export-path", Input).value)
            self.assertEqual(value.parent.resolve(), self.root.resolve())
            self.assertEqual(value.name, f"plan-P{self.pid}.md")

    async def test_export_writes_and_dismisses_with_the_path(self) -> None:
        from textual.widgets import Input

        target = self.root / "out" / "plan.md"
        results: list[Path | None] = []
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen(), results.append)
            await pilot.pause()
            screen = self.app.screen
            screen.query_one("#export-path", Input).value = str(target)
            await pilot.click("#export-ok")
            await pilot.pause()
            self.assertIsNot(self.app.screen, screen)
            self.assertEqual(results, [target.resolve()])
            self.assertTrue(target.is_file())

    async def test_overwrite_cancel_keeps_the_file_and_the_picker(self) -> None:
        from textual.widgets import Input

        from lazyplan.presentation.tui.screens import ConfirmScreen

        target = self.root / "plan.md"
        target.write_text("old\n", encoding="utf-8")
        results: list[Path | None] = []
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen(), results.append)
            await pilot.pause()
            screen = self.app.screen
            screen.query_one("#export-path", Input).value = str(target)
            await pilot.click("#export-ok")
            await pilot.pause()
            self.assertIsInstance(self.app.screen, ConfirmScreen)
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(self.app.screen, screen)
            self.assertEqual(results, [])
            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")

    async def test_overwrite_confirm_replaces_the_file(self) -> None:
        from textual.widgets import Input

        target = self.root / "plan.md"
        target.write_text("old\n", encoding="utf-8")
        results: list[Path | None] = []
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen(), results.append)
            await pilot.pause()
            screen = self.app.screen
            screen.query_one("#export-path", Input).value = str(target)
            await pilot.click("#export-ok")
            await pilot.pause()
            await pilot.click("#ok")
            await pilot.pause()
            self.assertEqual(results, [target.resolve()])
            self.assertNotEqual(target.read_text(encoding="utf-8"), "old\n")

    async def test_write_error_stays_inline_and_keeps_the_picker(self) -> None:
        from textual.widgets import Input, Static

        blocker = self.root / "blocker"
        blocker.write_text("not a directory\n", encoding="utf-8")
        results: list[Path | None] = []
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen(), results.append)
            await pilot.pause()
            screen = self.app.screen
            screen.query_one("#export-path", Input).value = str(blocker / "plan.md")
            await pilot.click("#export-ok")
            await pilot.pause()
            self.assertIs(self.app.screen, screen)
            self.assertEqual(results, [])
            error = str(screen.query_one("#export-error", Static).content)
            self.assertIn("could not export", error.lower())

    async def test_esc_cancels_without_writing(self) -> None:
        results: list[Path | None] = []
        async with self.app.run_test(size=(80, 24)) as pilot:
            self.app.push_screen(self._screen(), results.append)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(results, [None])
            self.assertFalse((self.downloads / f"plan-P{self.pid}.md").exists())

    async def test_action_opens_the_picker_for_plan_milestone_and_task(self) -> None:
        from unittest import mock

        from lazyplan.presentation.tui.screens.export import ExportScreen

        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            pushed: list[tuple[ExportScreen, object]] = []
            app.push_screen = lambda screen, callback=None: pushed.append(  # type: ignore[method-assign]
                (screen, callback)
            )
            for selected in (
                ("plan", self.pid),
                ("milestone", self.sid),
                ("task", self.tid),
            ):
                with self.subTest(selected=selected):
                    pushed.clear()
                    app.selected = selected
                    app.action_export_md()
                    self.assertEqual(len(pushed), 1)
                    screen, callback = pushed[0]
                    self.assertIsInstance(screen, ExportScreen)
                    self.assertEqual(screen.plan_id, self.pid)
                    self.assertEqual(screen.plan_title, "Website")
            with mock.patch.object(app, "notify") as notify:
                callback(Path("/tmp/plan.md"))  # type: ignore[operator]
                notify.assert_called_once()

    async def test_action_without_selection_does_not_open_the_picker(self) -> None:
        from unittest import mock

        app = tui_mod.create_app(self.db)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.selected = None
            with (
                mock.patch.object(app, "push_screen") as push,
                mock.patch.object(app, "notify") as notify,
            ):
                app.action_export_md()
            push.assert_not_called()
            notify.assert_called_once()

    async def test_dialog_fits_80x24_and_120x40(self) -> None:
        for width, height in ((80, 24), (120, 40)):
            with self.subTest(size=(width, height)):
                app = tui_mod.create_app(self.db)
                async with app.run_test(size=(width, height)) as pilot:
                    app.push_screen(self._screen())
                    await pilot.pause()
                    region = app.screen.query_one("#dlg").region
                    self.assertLessEqual(region.x + region.width, width)
                    self.assertLessEqual(region.y + region.height, height)


if __name__ == "__main__":
    unittest.main()
