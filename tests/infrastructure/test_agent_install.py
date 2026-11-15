"""OpenCode profile installation: paths, frontmatter, refresh, and conflicts."""

from __future__ import annotations

import tempfile
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
