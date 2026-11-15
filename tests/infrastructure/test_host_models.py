"""Host model discovery: live catalogs, config fallbacks, and failures."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import host_models, profiles


def completed(stdout: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["fake"], code, stdout, "")


class HostCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.repo = Path(self.tmp.name) / "repo"
        self.home.mkdir()
        self.repo.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_opencode_reads_live_models_and_jsonc_config(self) -> None:
        self._write(
            self.home / ".config/opencode/opencode.jsonc",
            '{\n  // main model\n  "model": "provider/big",\n  "small_model": "provider/tiny"\n}\n',
        )
        catalog = host_models.discover(
            "opencode",
            self.home,
            self.repo,
            which=lambda name: "/bin/opencode",
            run=lambda command, timeout: completed(
                "provider/big\nprovider/tiny\nprovider/mid\n"
            ),
        )
        self.assertIn("provider/mid", catalog.models)
        self.assertEqual(catalog.tier_defaults["fast"], "provider/tiny")
        self.assertEqual(catalog.tier_defaults["deep"], "provider/big")
        self.assertEqual(catalog.source, "opencode models")
        self.assertEqual(catalog.warning, "")

    def test_opencode_missing_binary_and_config_warns(self) -> None:
        catalog = host_models.discover(
            "opencode",
            self.home,
            self.repo,
            which=lambda name: None,
        )
        self.assertEqual(catalog.models, ())
        self.assertIn("not detected", catalog.warning)

    def test_opencode_command_failure_keeps_config(self) -> None:
        self._write(
            self.home / ".config/opencode/opencode.json",
            json.dumps({"model": "provider/big"}),
        )
        catalog = host_models.discover(
            "opencode",
            self.home,
            self.repo,
            which=lambda name: "/bin/opencode",
            run=lambda command, timeout: completed("", 2),
        )
        self.assertEqual(catalog.models, ("provider/big",))
        self.assertIn("exited 2", catalog.warning)

    def test_claude_reads_aliases_and_settings(self) -> None:
        self._write(
            self.home / ".claude/settings.json",
            json.dumps({"model": "claude-opus-5-5"}),
        )
        catalog = host_models.discover("claude", self.home)
        self.assertIn("haiku", catalog.models)
        self.assertIn("claude-opus-5-5", catalog.models)
        self.assertEqual(catalog.tier_defaults["deep"], "opus")
        self.assertEqual(catalog.source, str(self.home / ".claude/settings.json"))

    def test_codex_reads_live_json_and_toml(self) -> None:
        self._write(
            self.home / ".codex/config.toml",
            'model = "gpt-6.1-sol"\n[agents]\ndefault_subagent_model = "gpt-6-luna"\n',
        )
        catalog = host_models.discover(
            "codex",
            self.home,
            which=lambda name: "/bin/codex",
            run=lambda command, timeout: completed(
                json.dumps({"models": [{"slug": "gpt-6.1-sol"}, {"slug": "gpt-6-luna"}]})
            ),
        )
        self.assertIn("gpt-6.1-sol", catalog.models)
        self.assertEqual(catalog.tier_defaults["standard"], "gpt-6-luna")
        self.assertEqual(catalog.tier_defaults["deep"], "gpt-6.1-sol")
        self.assertEqual(catalog.source, "codex debug models")

    def test_codex_malformed_live_output_falls_back_to_config(self) -> None:
        self._write(self.home / ".codex/config.toml", 'model = "gpt-6.1-sol"\n')
        catalog = host_models.discover(
            "codex",
            self.home,
            which=lambda name: "/bin/codex",
            run=lambda command, timeout: completed("{not json"),
        )
        self.assertEqual(catalog.models, ("gpt-6.1-sol",))
        self.assertEqual(catalog.warning, "")

    def test_gemini_reads_settings_and_definitions(self) -> None:
        self._write(
            self.home / ".gemini/settings.json",
            json.dumps(
                {
                    "model": {"name": "gemini-3.8-flash"},
                    "modelConfigs": {"modelDefinitions": {"gemini-3.8-flash": {}}},
                }
            ),
        )
        catalog = host_models.discover("gemini", self.home)
        self.assertEqual(catalog.tier_defaults["standard"], "gemini-3.8-flash")
        self.assertIn("gemini-3.8-flash", catalog.models)
        self.assertEqual(catalog.warning, "")

    def test_cursor_defaults_to_inherit(self) -> None:
        catalog = host_models.discover("cursor", self.home, self.repo)
        self.assertEqual(catalog.models, ("inherit",))
        self.assertEqual(catalog.tier_defaults["fast"], "inherit")
        self.assertIn("manually", catalog.warning)

    def test_copilot_reads_config_and_warns_without_one(self) -> None:
        self._write(self.home / ".copilot/config.json", json.dumps({"model": "local/model"}))
        catalog = host_models.discover("copilot", self.home)
        self.assertEqual(catalog.tier_defaults["deep"], "local/model")
        self.assertEqual(catalog.warning, "")

        self._write(self.home / ".copilot/config.json", "{}")
        empty = host_models.discover("copilot", self.home)
        self.assertIn("does not expose", empty.warning)

    def test_discovery_never_raises_on_bad_config(self) -> None:
        self._write(self.home / ".gemini/settings.json", "{nope")
        catalog = host_models.discover("gemini", self.home)
        self.assertIn("not available", catalog.warning)

    def test_command_timeout_is_a_warning(self) -> None:
        def timeout(command: list[str], seconds: int) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(command, seconds)

        catalog = host_models.discover(
            "opencode",
            self.home,
            self.repo,
            which=lambda name: "/bin/opencode",
            run=timeout,
        )
        self.assertIn("failed", catalog.warning)

    def test_discover_all_preserves_host_order_and_skips_unknown(self) -> None:
        found = host_models.discover_all(["copilot", "opencode", "claude"], self.home)
        self.assertEqual(list(found), ["opencode", "claude", "copilot"])
        self.assertEqual(set(found), {"opencode", "claude", "copilot"})

    def test_unknown_host_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown host"):
            host_models.discover("wizard", self.home)

    def test_every_host_returns_tier_defaults(self) -> None:
        for host in profiles.HOSTS:
            with self.subTest(host=host):
                catalog = host_models.discover(host, self.home)
                self.assertEqual(set(catalog.tier_defaults), set(profiles.TIERS))


if __name__ == "__main__":
    unittest.main()
