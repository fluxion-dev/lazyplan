"""OpenCode profile installation: paths, frontmatter, refresh, and conflicts."""

from __future__ import annotations

import tempfile
import tomllib
import unittest
from pathlib import Path

from lazyplan.core.policies.lanes import AGENT_ROLES
from lazyplan.infrastructure import agent_install, profiles


class OpenCodeProfileInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.repo = self.root / "repo"
        self.home.mkdir()
        self.repo.mkdir()
        self.profiles = profiles.defaults()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_install_writes_one_managed_file_per_role(self) -> None:
        result = agent_install.install_opencode(
            "project",
            self.repo,
            self.home,
            self.profiles,
            {"main": "provider/big", "small": "provider/tiny"},
        )
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        self.assertEqual(result.kept, [])
        reviewer = (self.repo / ".opencode/agent/lazyplan-reviewer.md").read_text()
        self.assertIn("edit: deny", reviewer)
        self.assertIn("provider/big", reviewer)  # reviewer is deep, so the main model
        implementer = (self.repo / ".opencode/agent/lazyplan-implementer.md").read_text()
        self.assertIn("model: provider/tiny", implementer)
        self.assertIn(agent_install.MARKER, implementer)

    def test_reinstall_is_idempotent(self) -> None:
        agent_install.install_opencode("project", self.repo, self.home, self.profiles)
        again = agent_install.install_opencode("project", self.repo, self.home, self.profiles)
        self.assertTrue(again.installed)
        self.assertTrue(all("up-to-date" in line for line in again.installed))

    def test_managed_file_is_refreshed(self) -> None:
        agent_install.install_opencode("project", self.repo, self.home, self.profiles)
        path = self.repo / ".opencode/agent/lazyplan-qa.md"
        path.write_text(path.read_text() + "\nstale\n", encoding="utf-8")
        result = agent_install.install_opencode(
            "project",
            self.repo,
            self.home,
            self.profiles,
            {"main": "provider/big"},
        )
        self.assertTrue(any("refreshed" in line for line in result.installed))
        self.assertNotIn("stale", path.read_text())

    def test_unmarked_user_file_is_kept(self) -> None:
        path = self.repo / ".opencode/agent/lazyplan-docs.md"
        path.parent.mkdir(parents=True)
        path.write_text("my custom agent\n", encoding="utf-8")
        result = agent_install.install_opencode("project", self.repo, self.home, self.profiles)
        self.assertEqual(path.read_text(), "my custom agent\n")
        self.assertTrue(any("kept user file" in line for line in result.kept))

    def test_global_and_both_scopes(self) -> None:
        agent_install.install_opencode("global", self.repo, self.home, self.profiles)
        self.assertTrue((self.home / ".config/opencode/agent/lazyplan-qa.md").is_file())
        both = agent_install.install_opencode("both", self.repo, self.home, self.profiles)
        self.assertEqual(len(both.installed), len(AGENT_ROLES) * 2)

    def test_empty_scope_writes_nothing(self) -> None:
        result = agent_install.install_opencode("none", self.repo, self.home, self.profiles)
        self.assertEqual(result.installed, [])

    def test_claude_install_writes_frontmatter_and_read_only_roles(self) -> None:
        result = agent_install.install_claude("project", self.repo, self.home, self.profiles)
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        reviewer = (self.repo / ".claude/agents/lazyplan-reviewer.md").read_text()
        self.assertIn("name: lazyplan-reviewer", reviewer)
        self.assertIn("model: opus", reviewer)
        self.assertIn("permissionMode: plan", reviewer)
        self.assertIn("Read, Grep, Glob, Bash", reviewer)
        implementer = (self.repo / ".claude/agents/lazyplan-implementer.md").read_text()
        self.assertIn("model: haiku", implementer)
        self.assertIn("Edit, Write", implementer)
        self.assertIn(agent_install.MARKER, implementer)

    def test_claude_refresh_and_user_file_keep(self) -> None:
        agent_install.install_claude("project", self.repo, self.home, self.profiles)
        path = self.repo / ".claude/agents/lazyplan-docs.md"
        path.write_text(path.read_text() + "\nstale\n", encoding="utf-8")
        agent_install.install_claude("project", self.repo, self.home, self.profiles)
        self.assertNotIn("stale", path.read_text())

        custom = self.repo / ".claude/agents/lazyplan-qa.md"
        custom.write_text("custom\n", encoding="utf-8")
        result = agent_install.install_claude("project", self.repo, self.home, self.profiles)
        self.assertEqual(custom.read_text(), "custom\n")
        self.assertTrue(any("kept user file" in line for line in result.kept))

    def test_claude_global_scope(self) -> None:
        agent_install.install_claude("global", self.repo, self.home, self.profiles)
        self.assertTrue((self.home / ".claude/agents/lazyplan-qa.md").is_file())

    def test_codex_install_writes_valid_toml_and_read_only_sandbox(self) -> None:
        tiers = {"deep": {"codex": "gpt-6.1-sol"}, "fast": {"codex": "gpt-6-luna"}}
        result = agent_install.install_codex(
            "project", self.repo, self.home, self.profiles, None, tiers
        )
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        path = self.repo / ".codex/agents/lazyplan-reviewer.toml"
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# managed by lazyplan: codex reviewer"))
        parsed = tomllib.loads(text)
        self.assertEqual(parsed["name"], "lazyplan-reviewer")
        self.assertEqual(parsed["model"], "gpt-6.1-sol")
        self.assertEqual(parsed["sandbox_mode"], "read-only")
        self.assertIn("developer_instructions", parsed)
        implementer = tomllib.loads(
            (self.repo / ".codex/agents/lazyplan-implementer.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(implementer["model"], "gpt-6-luna")
        self.assertNotIn("sandbox_mode", implementer)

    def test_codex_refresh_and_user_file_keep(self) -> None:
        agent_install.install_codex("project", self.repo, self.home, self.profiles)
        path = self.repo / ".codex/agents/lazyplan-docs.toml"
        path.write_text(path.read_text(encoding="utf-8") + "\n# stale\n", encoding="utf-8")
        agent_install.install_codex("project", self.repo, self.home, self.profiles)
        self.assertNotIn("stale", path.read_text(encoding="utf-8"))
        custom = self.repo / ".codex/agents/lazyplan-qa.toml"
        custom.write_text('name = "mine"\n', encoding="utf-8")
        result = agent_install.install_codex("project", self.repo, self.home, self.profiles)
        self.assertEqual(custom.read_text(encoding="utf-8"), 'name = "mine"\n')
        self.assertTrue(any("kept user file" in line for line in result.kept))

    def test_codex_global_scope_and_profile_paths(self) -> None:
        agent_install.install_codex("global", self.repo, self.home, self.profiles)
        self.assertTrue((self.home / ".codex/agents/lazyplan-qa.toml").is_file())
        paths = agent_install.profile_paths("both", self.repo, self.home, ["codex"])
        self.assertEqual(len(paths), len(AGENT_ROLES) * 2)

    def test_gemini_install_writes_model_and_read_only_tools(self) -> None:
        tiers = {"standard": {"gemini": "gemini-3.8-flash"}}
        result = agent_install.install_gemini(
            "project", self.repo, self.home, self.profiles, None, tiers
        )
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        qa = (self.repo / ".gemini/agents/lazyplan-qa.md").read_text(encoding="utf-8")
        self.assertIn("name: lazyplan-qa", qa)
        self.assertIn("model: gemini-3.8-flash", qa)
        scout = (self.repo / ".gemini/agents/lazyplan-scout.md").read_text(encoding="utf-8")
        self.assertIn("tools:", scout)
        self.assertIn("read_file", scout)
        self.assertNotIn("run_shell_command", scout)
        reviewer = (self.repo / ".gemini/agents/lazyplan-reviewer.md").read_text(encoding="utf-8")
        self.assertIn("run_shell_command", reviewer)
        implementer = (self.repo / ".gemini/agents/lazyplan-implementer.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("tools:", implementer)

    def test_gemini_empty_model_is_inherit_and_global_scope(self) -> None:
        agent_install.install_gemini("global", self.repo, self.home, self.profiles)
        qa = (self.home / ".gemini/agents/lazyplan-qa.md").read_text(encoding="utf-8")
        self.assertIn("model: inherit", qa)
        self.assertEqual(
            len(agent_install.profile_paths("both", self.repo, self.home, ["gemini"])),
            len(AGENT_ROLES) * 2,
        )

    def test_cursor_install_writes_model_and_readonly_roles(self) -> None:
        tiers = {"deep": {"cursor": "composer-2"}}
        result = agent_install.install_cursor(
            "project", self.repo, self.home, self.profiles, None, tiers
        )
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        reviewer = (self.repo / ".cursor/agents/lazyplan-reviewer.md").read_text(encoding="utf-8")
        self.assertIn("name: lazyplan-reviewer", reviewer)
        self.assertIn("model: composer-2", reviewer)
        self.assertIn("readonly: true", reviewer)
        implementer = (self.repo / ".cursor/agents/lazyplan-implementer.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("model: inherit", implementer)
        self.assertNotIn("readonly:", implementer)

    def test_cursor_global_scope_and_profile_paths(self) -> None:
        agent_install.install_cursor("global", self.repo, self.home, self.profiles)
        self.assertTrue((self.home / ".cursor/agents/lazyplan-qa.md").is_file())
        self.assertEqual(
            len(agent_install.profile_paths("both", self.repo, self.home, ["cursor"])),
            len(AGENT_ROLES) * 2,
        )

    def test_copilot_install_uses_agent_suffix_and_readonly_tools(self) -> None:
        tiers = {"standard": {"copilot": "local/model"}}
        result = agent_install.install_copilot(
            "project", self.repo, self.home, self.profiles, None, tiers
        )
        self.assertEqual(len(result.installed), len(AGENT_ROLES))
        qa = (self.repo / ".github/agents/lazyplan-qa.agent.md").read_text(encoding="utf-8")
        self.assertIn("name: lazyplan-qa", qa)
        self.assertIn("model: local/model", qa)
        scout = (self.repo / ".github/agents/lazyplan-scout.agent.md").read_text(encoding="utf-8")
        self.assertIn('tools: ["read", "grep", "glob"]', scout)
        self.assertIn("strict-tools-list: true", scout)
        implementer = (self.repo / ".github/agents/lazyplan-implementer.agent.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("tools:", implementer)
        self.assertNotIn("model: inherit", implementer)

    def test_copilot_global_scope_and_profile_paths(self) -> None:
        agent_install.install_copilot("global", self.repo, self.home, self.profiles)
        self.assertTrue((self.home / ".copilot/agents/lazyplan-qa.agent.md").is_file())
        self.assertEqual(
            len(agent_install.profile_paths("both", self.repo, self.home, ["copilot"])),
            len(AGENT_ROLES) * 2,
        )

    def test_install_profiles_selects_the_requested_hosts(self) -> None:
        db = self.root / "profiles.db"
        result = agent_install.install_profiles(
            "project",
            self.repo,
            self.home,
            ["opencode", "claude"],
            db,
            {"main": "provider/big", "small": "provider/tiny"},
        )
        self.assertEqual([row.host for row in result], ["opencode", "claude"])
        self.assertTrue((self.repo / ".opencode/agent/lazyplan-qa.md").is_file())
        self.assertTrue((self.repo / ".claude/agents/lazyplan-qa.md").is_file())
        self.assertEqual(
            agent_install.install_profiles("none", self.repo, self.home, ["claude"], db),
            [],
        )


if __name__ == "__main__":
    unittest.main()
