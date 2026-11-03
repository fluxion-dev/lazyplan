"""Update logs: the command, the environment, and full output survive a failure."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import update_log


class TestUpdateLog(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_logs_dir_lives_under_the_shared_home(self) -> None:
        self.assertEqual(update_log.logs_dir(self.home), self.home / ".lazyplan" / "logs")

    def test_record_writes_the_command_and_output(self) -> None:
        path = update_log.record_update(
            "apply",
            method="pipx",
            command=["pipx", "install", "wheel.whl", "--force"],
            cwd="/work",
            exe="/venv/Scripts/python.exe",
            returncode=1,
            stdout="install output",
            stderr="permission denied",
            home=self.home,
            now=1000.0,
            pid=42,
        )
        self.assertEqual(path.parent, self.home / ".lazyplan" / "logs")
        self.assertTrue(path.name.startswith("update-apply-"))
        text = path.read_text(encoding="utf-8")
        self.assertIn("pipx install wheel.whl --force", text)
        self.assertIn("permission denied", text)
        self.assertIn("install output", text)
        self.assertIn("returncode: 1", text)
        self.assertIn("method: pipx", text)
        self.assertIn("exe: /venv/Scripts/python.exe", text)

    def test_labels_are_filename_safe(self) -> None:
        path = update_log.record_update(
            "up grade/attempt",
            method="pipx",
            command=["pipx"],
            cwd="/work",
            exe="python",
            returncode=None,
            home=self.home,
            now=1001.0,
            pid=7,
        )
        self.assertNotIn("/", path.name)
        self.assertNotIn(" ", path.name)


if __name__ == "__main__":
    unittest.main()
