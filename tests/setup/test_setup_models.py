"""Setup seeds and migrates the host-agnostic model map."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lazyplan.presentation import setup


class ProfileMapSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.db = self.home / ".lazyplan/lazyplan.db"
        self.map = self.home / ".lazyplan/agents.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, payload: object) -> None:
        self.map.parent.mkdir(parents=True, exist_ok=True)
        self.map.write_text(json.dumps(payload), encoding="utf-8")

    def _choice(self, **overrides: object) -> setup.SetupChoice:
        values = {
            "placement": setup.HOME,
            "agents": ["opencode"],
            "no_skills": False,
        }
        values.update(overrides)
        return setup.SetupChoice(**values)

    def test_first_setup_writes_schema_two_and_installs_models(self) -> None:
        result = setup.apply_choice(
            self._choice(
                tier_models={"opencode": {"fast": "provider/tiny", "deep": "provider/big"}}
            ),
            None,
            self.home,
            "1.0",
        )
        self.assertEqual(result["agents_json"], str(self.map))
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["schema"], 2)
        self.assertEqual(written["tiers"]["fast"]["opencode"], "provider/tiny")
        self.assertEqual(written["context"]["fast"]["claude"], 128_000)
        self.assertEqual(written["context"]["standard"]["claude"], 200_000)
        implementer = self.home / ".config/opencode/agent/lazyplan-implementer.md"
        reviewer = self.home / ".config/opencode/agent/lazyplan-reviewer.md"
        self.assertIn("model: provider/tiny", implementer.read_text(encoding="utf-8"))
        self.assertIn("model: provider/big", reviewer.read_text(encoding="utf-8"))

    def test_unchanged_rerun_does_not_rewrite_the_map(self) -> None:
        choice = self._choice(tier_models={"opencode": {"fast": "provider/tiny"}})
        setup.apply_choice(choice, None, self.home, "1.0")
        before = self.map.stat().st_mtime_ns
        setup.apply_choice(choice, None, self.home, "1.0")
        self.assertEqual(self.map.stat().st_mtime_ns, before)

    def test_v1_file_migrates_with_a_backup(self) -> None:
        self._write(
            {"profiles": {"qa": {"tier": "deep", "model": "provider/qa", "effort": "high"}}}
        )
        setup.apply_choice(self._choice(), None, self.home, "1.0")
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["schema"], 2)
        self.assertEqual(written["profiles"]["qa"]["model"], "provider/qa")
        backups = list((self.home / ".lazyplan/backups").rglob("agents.json"))
        self.assertTrue(backups)

    def test_user_tier_and_role_override_survive_a_plain_rerun(self) -> None:
        self._write(
            {
                "schema": 2,
                "tiers": {"fast": {"opencode": "provider/custom"}},
                "profiles": {
                    "scout": {
                        "tier": "standard",
                        "model": "",
                        "effort": "",
                        "models": {"opencode": "provider/scout"},
                    }
                },
            }
        )
        setup.apply_choice(self._choice(), None, self.home, "1.0")
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["profiles"]["scout"]["tier"], "standard")
        self.assertEqual(written["profiles"]["scout"]["models"]["opencode"], "provider/scout")
        self.assertEqual(written["tiers"]["fast"]["opencode"], "provider/custom")

    def test_role_flags_change_tier_and_model(self) -> None:
        setup.apply_choice(
            self._choice(
                role_tiers={"qa": "deep"},
                role_models={"claude": {"reviewer": "fable"}},
            ),
            None,
            self.home,
            "1.0",
        )
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["profiles"]["qa"]["tier"], "deep")
        self.assertEqual(written["profiles"]["reviewer"]["models"]["claude"], "fable")

    def test_no_skills_skips_the_map(self) -> None:
        setup.apply_choice(self._choice(no_skills=True), None, self.home, "1.0")
        self.assertFalse(self.map.exists())

    def test_wizard_reviews_and_writes_the_edited_map(self) -> None:
        import io

        answers = iter(["", "", "t qa deep", "", "y"])
        result = setup.run_wizard(
            self.home,
            self.home,
            setup.SetupState(),
            "1.0",
            read=lambda: next(answers),
            write=io.StringIO(),
            initial=setup.SetupChoice(placement=setup.HOME, agents=["opencode"]),
            hooks_mode="off",
        )
        self.assertIsNotNone(result)
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["profiles"]["qa"]["tier"], "deep")
        self.assertTrue((self.home / ".config/opencode/agent/lazyplan-qa.md").is_file())

    def test_end_to_end_setup_drives_profiles_doctor_and_dispatch(self) -> None:
        import io
        import os

        from lazyplan.infrastructure import agent_install, host_models, profiles
        from lazyplan.presentation.cli.main import main as lpui_main
        from tests.support.home import sandbox_home

        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        opencode = bin_dir / "opencode"
        opencode.write_text(
            "#!/bin/sh\nprintf 'provider/tiny\\nprovider/big\\n'\n", encoding="utf-8"
        )
        opencode.chmod(0o755)
        codex = bin_dir / "codex"
        codex.write_text(
            '#!/bin/sh\nprintf \'%s\' \'{"models": [{"slug": "gpt-6.1-sol"},'
            '{"slug": "gpt-6-luna"}]}\'\n',
            encoding="utf-8",
        )
        codex.chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}:{old_path}"
        self.addCleanup(lambda: os.environ.__setitem__("PATH", old_path))
        for name in ("opencode", "claude", "codex", "gemini", "cursor", "copilot"):
            (self.home / f".{name}").mkdir(exist_ok=True)
        (self.home / ".config/opencode").mkdir(parents=True, exist_ok=True)
        (self.home / ".config/opencode/opencode.json").write_text(
            '{"model": "provider/big", "small_model": "provider/tiny"}', encoding="utf-8"
        )
        (self.home / ".codex/config.toml").write_text('model = "gpt-6.1-sol"\n', encoding="utf-8")
        (self.home / ".gemini/settings.json").write_text(
            '{"model": {"name": "gemini-3.8-flash"}}', encoding="utf-8"
        )
        (self.home / ".cursor/settings.json").write_text(
            '{"model": "composer-2"}', encoding="utf-8"
        )
        (self.home / ".copilot/config.json").write_text(
            '{"model": "local/model"}', encoding="utf-8"
        )
        sandbox_home(self, str(self.home))
        answers = iter(["", "", "", "y"])
        result = setup.run_wizard(
            self.home,
            self.home,
            setup.SetupState(),
            "1.0",
            read=lambda: next(answers),
            write=io.StringIO(),
            initial=setup.SetupChoice(placement=setup.HOME),
            hooks_mode="off",
        )
        self.assertIsNotNone(result)
        setup.install_integrations(result, self.home, None)
        state = setup.load_state(self.home)
        inspection = setup.inspect(setup.choice_from_state(state), state, None, self.home, "1.0")
        if setup.remember_installed(inspection, state, "1.0"):
            setup.save_state(state, self.home)
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["tiers"]["fast"]["opencode"], "provider/tiny")
        self.assertEqual(written["tiers"]["deep"]["codex"], "gpt-6.1-sol")
        self.assertTrue((self.home / ".copilot/agents/lazyplan-qa.agent.md").is_file())
        report = host_models.discover_all(profiles.HOSTS, self.home, None)
        self.assertEqual(report["opencode"].tier_defaults["fast"], "provider/tiny")
        db = self.home / ".lazyplan/lazyplan.db"
        manifest = profiles.dispatch_profiles(db, self.home)
        self.assertEqual(manifest["reviewer"]["models"]["claude"], "opus")
        old_cwd = os.getcwd()
        old_no_setup = os.environ.get("LAZYPLAN_NO_SETUP")
        os.chdir(self.home)
        os.environ["LAZYPLAN_NO_SETUP"] = "1"
        self.addCleanup(os.chdir, old_cwd)
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("LAZYPLAN_NO_SETUP", old_no_setup)
                if old_no_setup is not None
                else os.environ.pop("LAZYPLAN_NO_SETUP", None)
            )
        )
        code = lpui_main(["--json", "doctor"])
        self.assertEqual(code, 0)
        state = setup.load_state(self.home)
        before = {
            path: path.stat().st_mtime_ns
            for path in agent_install.profile_paths("global", None, self.home, state.agents)
        }
        setup.apply_choice(setup.choice_from_state(state), None, self.home, "1.0")
        after = {path: path.stat().st_mtime_ns for path in before}
        self.assertEqual(after, before)

    def test_deselected_host_removes_only_managed_profiles(self) -> None:
        setup.apply_choice(self._choice(agents=["opencode", "claude"]), None, self.home, "1.0")
        custom = self.home / ".claude/agents/lazyplan-custom.md"
        custom.write_text("my custom agent\n", encoding="utf-8")
        managed = self.home / ".claude/agents/lazyplan-qa.md"
        self.assertTrue(managed.is_file())
        result = setup.apply_choice(self._choice(agents=["opencode"]), None, self.home, "1.0")
        self.assertFalse(managed.exists())
        self.assertEqual(custom.read_text(encoding="utf-8"), "my custom agent\n")
        self.assertTrue((self.home / ".config/opencode/agent/lazyplan-qa.md").is_file())
        self.assertTrue(result["removed_profiles"])
        self.assertEqual(setup.load_state(self.home).agents, ["opencode"])
        self.assertFalse(
            any("claude" in path for path in setup.load_state(self.home).profile_files)
        )

    def test_wizard_can_skip_the_model_review(self) -> None:
        import io

        answers = iter(["", "", "y"])
        result = setup.run_wizard(
            self.home,
            self.home,
            setup.SetupState(),
            "1.0",
            read=lambda: next(answers),
            write=io.StringIO(),
            initial=setup.SetupChoice(
                placement=setup.HOME,
                agents=["opencode"],
                model_review=False,
            ),
            hooks_mode="off",
        )
        self.assertIsNotNone(result)
        written = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(written["profiles"]["qa"]["tier"], "standard")


if __name__ == "__main__":
    unittest.main()
