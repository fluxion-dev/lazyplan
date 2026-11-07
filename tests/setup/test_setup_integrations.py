"""Read-only inspection of installed and pending integrations."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure import hook_install, skills
from lazyplan.infrastructure.integrations import catalog, hook_id, skill_id
from lazyplan.presentation.setup import integrations
from lazyplan.presentation.setup.layout import SetupChoice
from lazyplan.presentation.setup.state import SetupState


class InspectionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.choice = SetupChoice(placement="home", agents=["claude"])
        self.state = SetupState()
        self.old_noskills = os.environ.pop("LAZYPLAN_NO_SKILLS", None)

    def tearDown(self):
        if self.old_noskills is not None:
            os.environ["LAZYPLAN_NO_SKILLS"] = self.old_noskills
        self.tmp.cleanup()

    def inspect(self, version: str = "1.0"):
        return integrations.inspect(self.choice, self.state, self.repo, self.home, version)

    def item(self, item_id: str):
        return next(item for item in catalog(self.home) if item.id == item_id)

    def test_nothing_installed_leaves_every_enabled_item_pending(self):
        report = self.inspect()
        self.assertEqual(report.installed, ())
        self.assertIn(skill_id("lazyplan"), {item.id for item in report.pending})
        self.assertIn(hook_id("claude", "session-start"), {item.id for item in report.pending})

    def test_installed_skill_is_not_pending(self):
        dest = self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("installed", encoding="utf-8")
        report = self.inspect()
        installed = {item.id for item in report.installed}
        self.assertIn(skill_id("lazyplan"), installed)
        self.assertNotIn(skill_id("lazyplan"), {item.id for item in report.pending})

    def test_installed_hooks_are_not_pending(self):
        hook_install.install(self.home, ["claude"])
        report = self.inspect()
        installed = {item.id for item in report.installed}
        pending = {item.id for item in report.pending}
        for event in ("session-start", "prompt-submit", "post-tool", "stop"):
            self.assertIn(hook_id("claude", event), installed)
            self.assertNotIn(hook_id("claude", event), pending)

    def test_opencode_plugin_is_installed_as_one_item(self):
        hook_install.install(self.home, ["opencode"])
        report = self.inspect()
        self.assertIn(hook_id("opencode", "plugin"), {item.id for item in report.installed})
        self.assertNotIn(hook_id("opencode", "plugin"), {item.id for item in report.pending})

    def test_deferred_item_waits_for_the_next_version(self):
        skill = self.item(skill_id("lazyplan"))
        self.state.integration_choices[skill.id] = {
            "decision": "deferred",
            "fingerprint": skill.fingerprint,
            "version": "1.0",
        }
        self.assertNotIn(skill.id, {item.id for item in self.inspect("1.0").pending})
        self.assertIn(skill.id, {item.id for item in self.inspect("2.0").pending})

    def test_never_item_is_terminal_until_the_fingerprint_changes(self):
        skill = self.item(skill_id("lazyplan"))
        self.state.integration_choices[skill.id] = {
            "decision": "never",
            "fingerprint": skill.fingerprint,
            "version": "1.0",
        }
        self.assertNotIn(skill.id, {item.id for item in self.inspect("2.0").pending})
        self.state.integration_choices[skill.id]["fingerprint"] = "old"
        self.assertIn(skill.id, {item.id for item in self.inspect("2.0").pending})

    def test_installed_choice_does_not_repair_a_missing_file(self):
        skill = self.item(skill_id("lazyplan"))
        self.state.integration_choices[skill.id] = {
            "decision": "installed",
            "fingerprint": skill.fingerprint,
            "version": "1.0",
        }
        self.assertNotIn(skill.id, {item.id for item in self.inspect().pending})

    def test_skills_and_hooks_opt_outs_remove_their_items(self):
        self.state.skills_enabled = False
        self.state.hooks_enabled = False
        pending = {item.id for item in self.inspect().pending}
        self.assertFalse(any(item_id.startswith("skill:") for item_id in pending))
        self.assertFalse(any(item_id.startswith("hook:") for item_id in pending))

    def test_no_skills_choice_removes_skill_items(self):
        self.choice = SetupChoice(
            placement="home",
            agents=["claude"],
            no_skills=True,
        )
        pending = {item.id for item in self.inspect().pending}
        self.assertNotIn(skill_id("lazyplan"), pending)

    def test_inspection_writes_nothing(self):
        before = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        self.inspect()
        after = sorted(path.relative_to(self.home) for path in self.home.rglob("*"))
        self.assertEqual(before, after)

    def test_skill_is_detected_at_a_custom_skills_dir(self):
        self.choice = SetupChoice(
            placement="home",
            agents=["claude"],
            skills_dir=str(self.home / "custom-skills"),
        )
        dest = self.home / "custom-skills" / "lazyplan" / "SKILL.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("installed", encoding="utf-8")
        self.assertIn(skill_id("lazyplan"), {item.id for item in self.inspect().installed})

    def test_skill_files_use_the_remembered_scope(self):
        self.choice = SetupChoice(
            placement="repo",
            agents=["claude"],
            skills_dir=None,
        )
        dest = self.repo / ".claude" / "skills" / "lazyplan" / "SKILL.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("installed", encoding="utf-8")
        self.assertIn(skill_id("lazyplan"), {item.id for item in self.inspect().installed})
        self.assertTrue(self.repo.is_dir())

    def test_render_skill_can_be_named(self):
        self.assertEqual(skills.render_skill("lazyplan"), skills.render_skill())


if __name__ == "__main__":
    unittest.main()
