"""Hook installation: markers, backups, idempotency, and removal."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from lazyplan.infrastructure import hook_hosts, hook_install
from lazyplan.presentation import setup
from lazyplan.presentation.cli import main as lpui_main
from tests.support.home import sandbox_home

ALL = list(hook_install.HOSTS)


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _commands(self, data: dict) -> list[str]:
        text = json.dumps(data)
        return [part.split('"')[0] for part in text.split("lpui hook")[1:]]

    def test_installs_every_supported_host(self):
        report = hook_install.install(self.home, ALL)
        self.assertEqual(len(report["installed"]), 5)
        plugin = self.home / ".config/opencode/plugins/lazyplan.js"
        self.assertTrue(plugin.is_file())
        text = plugin.read_text(encoding="utf-8")
        self.assertIn("export default", text)
        self.assertIn('id: "lazyplan"', text)
        self.assertIn("async setup(ctx)", text)
        self.assertIn("session-start", text)
        self.assertIn("ctx.event.subscribe", text)
        self.assertIn("session.idle", text)
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
            ),
            encoding="utf-8",
        )
        hook_install.install(self.home, ["claude"])
        data = self._read(settings)
        self.assertEqual(data["theme"], "dark")
        text = json.dumps(data["hooks"]["Stop"])
        self.assertIn("echo user", text)
        self.assertIn("lpui hook stop --host claude", text)

    def test_second_install_is_idempotent(self):
        hook_install.install(self.home, ["claude"])
        before = (self.home / ".claude/settings.json").read_text(encoding="utf-8")
        result = hook_install.install(self.home, ["claude"])
        after = (self.home / ".claude/settings.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertEqual(after.count("lpui hook session-start"), 1)
        self.assertEqual(result["installed"], [])
        self.assertEqual(result["backups"], [])

    def test_opencode_plugin_denies_commits_and_reuses_context(self):
        hook_install.install(self.home, ["opencode"], mode="advisory")
        text = (self.home / ".config/opencode/plugins/lazyplan.js").read_text(encoding="utf-8")
        self.assertIn('ctx.permission.hook("evaluate"', text)
        self.assertIn('ctx.session.hook("context"', text)
        self.assertIn('ctx.session.hook("compaction"', text)
        self.assertIn('"--mode", MODE', text)
        self.assertIn('const MODE = "advisory"', text)
        self.assertIn('"session-end"', text)

    def test_opencode_plugin_closes_stdin_and_reports_failures(self):
        hook_install.install(self.home, ["opencode"], mode="strict")
        text = (self.home / ".config/opencode/plugins/lazyplan.js").read_text(encoding="utf-8")
        self.assertIn('stdio: ["ignore", "pipe", "pipe"]', text)
        self.assertNotIn("execFile", text)
        self.assertIn("console.warn", text)
        self.assertIn("resolve(null)", text)
        self.assertIn("state.started = true", text)
        self.assertIn("if (text !== null)", text)

    def test_opencode_plugin_maps_v2_lifecycle_events(self):
        hook_install.install(self.home, ["opencode"])
        text = (self.home / ".config/opencode/plugins/lazyplan.js").read_text(encoding="utf-8")
        for event in (
            '"session.created"',
            '"session.execution.started"',
            '"session.idle"',
            '"session.deleted"',
            '"session.archived"',
        ):
            self.assertIn(event, text)
        self.assertIn("data.parentID", text)
        self.assertIn('await run(directory, "stop", { session })', text)
        idle_block = text.split('event.type === "session.idle"', 1)[1].split("continue", 1)[0]
        self.assertNotIn('"session-end"', idle_block)

    def test_opencode_plugin_passes_the_session_on_every_event(self):
        hook_install.install(self.home, ["opencode"])
        text = (self.home / ".config/opencode/plugins/lazyplan.js").read_text(encoding="utf-8")
        for event in ("session-start", "prompt-submit", "stop", "session-end"):
            self.assertIn(f'await run(directory, "{event}", {{ session }})', text)
        self.assertIn("--host-session", text)
        self.assertIn("stateFor(session)", text)
        self.assertIn("const states = new Map()", text)
        self.assertIn("states.delete(session", text)

    def test_mode_reinstall_replaces_managed_commands(self):
        hook_install.install(self.home, ["claude"], mode="strict")
        hook_install.install(self.home, ["claude"], mode="advisory")
        text = (self.home / ".claude/settings.json").read_text(encoding="utf-8")
        self.assertIn("--mode advisory", text)
        self.assertNotIn("--mode strict", text)

    def test_new_events_are_installed_for_every_surface(self):
        hook_install.install(self.home, ALL)
        claude = json.dumps(self._read(self.home / ".claude/settings.json"))
        self.assertIn("PreToolUse", claude)
        self.assertIn("SessionEnd", claude)
        cursor = self._read(self.home / ".cursor/hooks.json")
        self.assertIn("beforeShellExecution", cursor["hooks"])
        self.assertIn("sessionEnd", cursor["hooks"])

    def test_remove_strips_only_managed_entries(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(
            json.dumps(
                {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user"}]}]}}
            ),
            encoding="utf-8",
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
        settings.write_text("{not json", encoding="utf-8")
        report = hook_install.install(self.home, ["claude"])
        self.assertEqual(report["installed"], [])
        self.assertEqual(report["skipped"][0]["path"], str(settings))
        self.assertEqual(settings.read_text(encoding="utf-8"), "{not json")

    def test_claude_post_tool_matches_bash_and_powershell(self):
        hook_install.install(self.home, ["claude"])
        hooks = self._read(self.home / ".claude/settings.json")["hooks"]
        self.assertEqual(
            hooks["PostToolUse"][0]["matcher"], hook_hosts.matcher("claude", "PostToolUse")
        )
        self.assertEqual(hooks["SessionStart"][0]["matcher"], "*")
        self.assertIn("PreCompact", hooks)

    def test_reinstall_replaces_stale_managed_entries(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        stale = [{"type": "command", "command": "lpui hook pre-compact --host claude"}]
        old_post = [{"type": "command", "command": hook_install.command("claude", "post-tool")}]
        user = [{"type": "command", "command": "echo user"}]
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreCompact": [{"matcher": "*", "hooks": stale}],
                        "PostToolUse": [
                            {"matcher": "Bash", "hooks": old_post},
                            {"matcher": "Edit", "hooks": user},
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        hook_install.install(self.home, ["claude"])
        hooks = self._read(settings)["hooks"]
        self.assertIn("PreCompact", hooks)
        self.assertEqual(
            [(group["matcher"], group["hooks"]) for group in hooks["PostToolUse"]],
            [("Edit", user), (hook_hosts.matcher("claude", "PostToolUse"), old_post)],
        )

    def test_reads_settings_with_a_byte_order_mark(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "dark"}).encode())
        report = hook_install.install(self.home, ["claude"])
        self.assertEqual(report["skipped"], [])
        data = self._read(settings)
        self.assertEqual(data["theme"], "dark")
        self.assertTrue(data["hooks"])

    def test_each_change_has_a_backup(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        hook_install.install(self.home, ["claude"])
        data = json.loads(settings.read_text(encoding="utf-8"))
        data["hooks"] = {}
        settings.write_text(json.dumps(data), encoding="utf-8")
        report = hook_install.install(self.home, ["claude"])
        backup_dir = Path(report["backups"][0])
        self.assertTrue(list(backup_dir.rglob("settings.json")))


class SetupCliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        (self.home / ".claude").mkdir()
        (self.home / ".config" / "opencode").mkdir(parents=True)
        self.old_db = os.environ.pop("LAZYPLAN_DB", None)
        self.old_nosetup = os.environ.pop(setup.NO_SETUP_ENV, None)
        self.old_cwd = os.getcwd()
        sandbox_home(self, str(self.home))
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.old_cwd)
        for key, value in (
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
        self.assertIn("lpui hook session-start --host claude", settings.read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".config/opencode/plugins/lazyplan.js").is_file())
        self.assertTrue(setup.load_state(self.home).hooks)

        self._setup("--no-hooks")
        self.assertNotIn("lpui hook", settings.read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())
        self.assertFalse(setup.load_state(self.home).hooks)

    def test_selected_agents_limit_plugins(self):
        self._setup("--agents", "claude")
        self.assertIn(
            "lpui hook", (self.home / ".claude/settings.json").read_text(encoding="utf-8")
        )
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())

    def test_no_agents_means_no_plugins(self):
        self._setup("--agents", "none")
        self.assertFalse((self.home / ".claude/settings.json").exists())
        self.assertFalse((self.home / ".config/opencode/plugins/lazyplan.js").exists())
        self.assertFalse(setup.load_state(self.home).hooks)


if __name__ == "__main__":
    unittest.main()
