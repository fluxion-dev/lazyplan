"""Shared Markdown export: defaults, destination rules, and safe writes."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.infrastructure.paths import download_dir
from lazyplan.presentation.shared.export import (
    ExportError,
    default_export_path,
    display_path,
    resolve_export_path,
    write_export,
)


class DownloadDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_environment_download_dir_wins(self) -> None:
        target = Path(self.tmp.name) / "from-env"
        target.mkdir()
        env = {"HOME": str(self.home), "XDG_DOWNLOAD_DIR": str(target)}
        self.assertEqual(download_dir(env), target)

    def test_user_dirs_file_is_read(self) -> None:
        target = Path(self.tmp.name) / "from-file"
        target.mkdir()
        config = self.home / ".config"
        config.mkdir()
        (config / "user-dirs.dirs").write_text(
            f'XDG_DOWNLOAD_DIR="{target}"\n',
            encoding="utf-8",
        )
        self.assertEqual(download_dir({"HOME": str(self.home)}), target)

    def test_home_downloads_is_the_fallback(self) -> None:
        target = self.home / "Downloads"
        target.mkdir()
        self.assertEqual(download_dir({"HOME": str(self.home)}), target)

    def test_windows_userprofile_downloads_is_supported(self) -> None:
        target = self.home / "Downloads"
        target.mkdir()
        self.assertEqual(download_dir({"USERPROFILE": str(self.home)}), target)

    def test_missing_downloads_returns_none(self) -> None:
        self.assertIsNone(download_dir({"HOME": str(self.home)}))


class ExportPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.downloads = self.home / "Downloads"
        self.downloads.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_path_uses_the_downloads_folder(self) -> None:
        path = default_export_path(7, default_dir=self.downloads)
        self.assertEqual(path, self.downloads / "plan-P7.md")

    def test_empty_destination_uses_the_default(self) -> None:
        path = resolve_export_path("", 7, default_dir=self.downloads)
        self.assertEqual(path, (self.downloads / "plan-P7.md").resolve())

    def test_tilde_is_expanded(self) -> None:
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}):
            path = resolve_export_path("~/notes/plan.md", 7, default_dir=self.downloads)
        self.assertEqual(path, (self.home / "notes" / "plan.md").resolve())

    def test_existing_directory_receives_the_default_filename(self) -> None:
        path = resolve_export_path(self.downloads, 7, default_dir=self.downloads)
        self.assertEqual(path, (self.downloads / "plan-P7.md").resolve())

    def test_missing_suffix_gets_markdown(self) -> None:
        path = resolve_export_path(self.root / "notes", 7, default_dir=self.downloads)
        self.assertEqual(path, (self.root / "notes.md").resolve())

    def test_existing_markdown_suffix_is_kept(self) -> None:
        path = resolve_export_path(self.root / "notes.markdown", 7, default_dir=self.downloads)
        self.assertEqual(path, (self.root / "notes.markdown").resolve())

    def test_display_path_shortens_home(self) -> None:
        with mock.patch("pathlib.Path.home", return_value=self.home):
            self.assertEqual(
                display_path(self.home / "Downloads" / "plan.md"), "~/Downloads/plan.md"
            )


class WriteExportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "nested" / "plan.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_missing_parents_and_writes_markdown(self) -> None:
        written = write_export(self.path, "# Plan\n")
        self.assertEqual(written, self.path.resolve())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "# Plan\n")

    def test_existing_file_is_refused_without_force(self) -> None:
        self.path.parent.mkdir()
        self.path.write_text("old\n", encoding="utf-8")
        with self.assertRaises(ExportError) as caught:
            write_export(self.path, "new\n")
        self.assertIn("overwrite", str(caught.exception).lower())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "old\n")

    def test_force_replaces_an_existing_file(self) -> None:
        self.path.parent.mkdir()
        self.path.write_text("old\n", encoding="utf-8")
        write_export(self.path, "new\n", force=True)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "new\n")

    def test_os_error_is_wrapped_with_the_path(self) -> None:
        with mock.patch(
            "lazyplan.infrastructure.textfile.write_atomic",
            side_effect=OSError("permission denied"),
        ):
            with self.assertRaises(ExportError) as caught:
                write_export(self.path, "# Plan\n")
        self.assertIn("permission denied", str(caught.exception))
        self.assertIn("plan.md", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
