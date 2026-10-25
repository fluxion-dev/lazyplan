"""Hook installation: markers, backups, idempotency, and removal."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lazyplan import hook_install, setup  # noqa: E402
from lazyplan.cli import main as lpui_main  # noqa: E402

ALL = list(hook_install.HOSTS)


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text())

    def _commands(self, data: dict) -> list[str]:
        text = json.dumps(data)
        return [part.split('"')[0] for part in text.split("lpui hook")[1:]]

    def test_installs_every_supported_host(self):
        report = hook_install.install(self.home, ALL)
        self.assertEqual(len(report["installed"]), 5)
        plugin = self.home / ".config/opencode/plugins/lazyplan.js"
        self.assertTrue(plugin.is_file())
        text = plugin.read_text()
        self.assertIn("export default", text)
        self.assertIn('id: "lazyplan"', text)
        self.assertIn("async setup(ctx)", text)
        self.assertIn("session-start", text)
        for relative in (".claude/settings.json", ".gemini/settings.json", ".codex/hooks.json"):
            data = self._read(self.home / relative)
            self.assertTrue(data["hooks"])
        cursor = self._read(self.home / ".cursor/hooks.json")
        self.assertEqual(cursor["version"], 1)
        self.assertTrue(cursor["hooks"])

    def test_preserves_unmarked_entries(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {
                    "theme": "dark",
                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user"}]}]},
                }
            )
        )
        hook_install.install(self.home, ["claude"])
        data = self._read(settings)
        self.assertEqual(data["theme"], "dark")
        text = json.dumps(data["hooks"]["Stop"])
        self.assertIn("echo user", text)
        self.assertIn("lpui hook stop --host claude", text)

    def test_second_install_is_idempotent(self):
        hook_install.install(self.home, ["claude"])
        before = (self.home / ".claude/settings.json").read_text()
        hook_install.install(self.home, ["claude"])
        after = (self.home / ".claude/settings.json").read_text()
        self.assertEqual(before, after)
        self.assertEqual(after.count("lpui hook session-start"), 1)

    def test_remove_strips_only_managed_entries(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user"}]}]}}
            )
        )
        hook_install.install(self.home, ["claude"])
        hook_install.remove(self.home, ["claude"])
        data = self._read(settings)
        text = json.dumps(data)
        self.assertIn("echo user", text)
        self.assertNotIn("lpui hook", text)
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())

    def test_invalid_json_is_skipped_and_untouched(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{not json")
        report = hook_install.install(self.home, ["claude"])
        self.assertEqual(report["installed"], [])
        self.assertEqual(report["skipped"][0]["path"], str(settings))
        self.assertEqual(settings.read_text(), "{not json")

    def test_each_change_has_a_backup(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"theme": "dark"}))
        hook_install.install(self.home, ["claude"])
        backup_dir = Path(hook_install.install(self.home, ["claude"])["backups"][0])
        self.assertTrue(list(backup_dir.rglob("settings.json")))


class SetupCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        (self.home / ".claude").mkdir()
        self.old_home = os.environ.get("HOME")
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        os.environ["HOME"] = str(self.home)
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
            ("HOME", self.old_home),
            ("LAZYPLAN_DB", self.old_db),
            (setup.NO_SETUP_ENV, self.old_nosetup),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def _setup(self, *extra: str) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            code = lpui_main(["setup", "--yes", "--no-skills", *extra])
        self.assertEqual(code, 0, out.getvalue())

    def test_setup_installs_and_removes_hooks(self):
        self._setup()
        settings = self.home / ".claude/settings.json"
        self.assertIn("lpui hook session-start --host claude", settings.read_text())
        self.assertTrue((self.home / ".config/opencode/plugins/lazyplan.js").is_file())
        self.assertTrue(setup.load_state(self.home).hooks)

        self._setup("--no-hooks")
        self.assertNotIn("lpui hook", settings.read_text())
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())
        self.assertFalse(setup.load_state(self.home).hooks)


if __name__ == "__main__":
    unittest.main()
