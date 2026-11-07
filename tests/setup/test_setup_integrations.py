"""Read-only inspection of installed and pending integrations."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.infrastructure import hook_install, skills
from lazyplan.infrastructure.integrations import catalog, hook_id, skill_id
from lazyplan.presentation.setup import integrations
from lazyplan.presentation.setup.layout import SetupChoice
from lazyplan.presentation.setup.state import SetupState, state_path


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


class ReviewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.choice = SetupChoice(placement="home", agents=["claude"])
        self.state = SetupState()
        self.version = "1.0"
        all_items = {item.id: item for item in catalog(self.home)}
        self.items = (
            all_items[skill_id("lazyplan")],
            all_items[hook_id("claude", "session-start")],
        )
        self.patcher = mock.patch.object(integrations, "catalog", return_value=self.items)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def review(self, answer: str, allow_prompt: bool = True, read=None):
        out = io.StringIO()
        result = integrations.review_pending(
            self.choice,
            self.state,
            self.repo,
            self.home,
            self.version,
            read=read or (lambda: answer),
            write=out,
            allow_prompt=allow_prompt,
        )
        return result, out.getvalue()

    def test_install_all_writes_skills_and_hooks(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        result, out = self.review("1")
        self.assertEqual(result.decision, "install")
        self.assertTrue((self.home / ".claude/skills/lazyplan/SKILL.md").is_file())
        self.assertIn("lpui hook session-start", settings.read_text(encoding="utf-8"))
        self.assertIn("New integrations are available", out)
        self.assertIn("skill: lazyplan skill", out)
        choices = self.state.integration_choices
        self.assertEqual(choices[skill_id("lazyplan")]["decision"], "installed")
        self.assertEqual(choices[hook_id("claude", "session-start")]["decision"], "installed")
        backups = list((self.home / ".lazyplan" / "backups").rglob("settings.json"))
        self.assertEqual(len(backups), 1)
        self.assertIn("theme", backups[0].read_text(encoding="utf-8"))

    def test_defer_remembers_the_version_and_writes_nothing(self):
        result, out = self.review("2")
        self.assertEqual(result.decision, "deferred")
        self.assertIn("New integrations are available", out)
        self.assertFalse((self.home / ".claude").exists())
        self.assertTrue(state_path(self.home).is_file())
        self.assertEqual(
            self.state.integration_choices[skill_id("lazyplan")]["version"],
            self.version,
        )
        pending = integrations.inspect(
            self.choice, self.state, self.repo, self.home, self.version
        ).pending
        self.assertEqual(pending, ())
        later = integrations.inspect(self.choice, self.state, self.repo, self.home, "2.0").pending
        self.assertIn(skill_id("lazyplan"), {item.id for item in later})

    def test_never_remembers_the_choice_until_the_fingerprint_changes(self):
        result, _out = self.review("3")
        self.assertEqual(result.decision, "never")
        self.assertEqual(
            self.state.integration_choices[hook_id("claude", "session-start")]["decision"],
            "never",
        )
        later = integrations.inspect(self.choice, self.state, self.repo, self.home, "2.0").pending
        self.assertNotIn(hook_id("claude", "session-start"), {item.id for item in later})
        self.state.integration_choices[hook_id("claude", "session-start")]["fingerprint"] = "old"
        rearmed = integrations.inspect(self.choice, self.state, self.repo, self.home, "2.0").pending
        self.assertIn(hook_id("claude", "session-start"), {item.id for item in rearmed})

    def test_empty_answer_defers(self):
        result, _out = self.review("")
        self.assertEqual(result.decision, "deferred")

    def test_no_prompt_leaves_pending_and_writes_nothing(self):
        def fail():
            raise AssertionError("must not read when prompts are disabled")

        result, out = self.review("", allow_prompt=False, read=fail)
        self.assertEqual(result.decision, "pending")
        self.assertEqual(result.pending, self.items)
        self.assertEqual(out, "")
        self.assertEqual(self.state.integration_choices, {})
        self.assertFalse(state_path(self.home).exists())

    def test_no_pending_items_returns_none(self):
        for item in self.items:
            self.state.integration_choices[item.id] = {
                "decision": "never",
                "fingerprint": item.fingerprint,
                "version": self.version,
            }
        result, out = self.review("1")
        self.assertEqual(result.decision, "none")
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
