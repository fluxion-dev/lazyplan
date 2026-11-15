"""Curated effort levels validate, render per host, and keep legacy strings."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lazyplan.core.policies import effort
from lazyplan.infrastructure import profiles
from lazyplan.infrastructure.agent_install import render_profile
from lazyplan.presentation import setup


def _render(host: str, value: str) -> str:
    profile = profiles.Profile(role="implementer", tier="standard", effort=value)
    return render_profile(host, "implementer", {"implementer": profile})


class EffortPolicyTest(unittest.TestCase):
    def test_levels_include_inherit_first(self) -> None:
        self.assertEqual(effort.LEVELS[0], effort.INHERIT)
        self.assertEqual(effort.LABELS[effort.INHERIT], "inherit")
        self.assertIn(effort.HIGH, effort.LEVELS)

    def test_inherit_aliases_normalize_to_empty(self) -> None:
        for value in ("", "inherit", "INHERIT", " none ", "default"):
            self.assertEqual(effort.normalize(value), effort.INHERIT)
        self.assertEqual(effort.normalize(" High "), effort.HIGH)

    def test_check_rejects_unknown_values(self) -> None:
        self.assertEqual(effort.check("medium"), effort.MEDIUM)
        with self.assertRaises(ValueError):
            effort.check("turbo")

    def test_only_claude_codex_and_opencode_render_effort(self) -> None:
        self.assertTrue(effort.supports("claude"))
        self.assertTrue(effort.supports("codex"))
        self.assertTrue(effort.supports("opencode"))
        for host in ("gemini", "cursor", "copilot"):
            self.assertFalse(effort.supports(host))
            self.assertEqual(effort.field_for(host), "")


class EffortRenderTest(unittest.TestCase):
    def test_supporting_hosts_render_their_native_field(self) -> None:
        self.assertIn("effort: high", _render("claude", effort.HIGH))
        self.assertIn('model_reasoning_effort = "high"', _render("codex", effort.HIGH))
        self.assertIn("variant: high", _render("opencode", effort.HIGH))

    def test_unsupported_hosts_omit_the_field(self) -> None:
        for host in ("gemini", "cursor", "copilot"):
            text = _render(host, effort.HIGH)
            self.assertNotIn("model_reasoning_effort", text)
            self.assertNotIn("variant:", text)
            self.assertNotIn("effort:", text)

    def test_inherit_renders_no_field(self) -> None:
        self.assertNotIn("effort:", _render("claude", effort.INHERIT))
        self.assertNotIn("variant:", _render("opencode", effort.INHERIT))

    def test_a_legacy_value_still_renders(self) -> None:
        self.assertIn("effort: ultra", _render("claude", "ultra"))


class LegacyEffortFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "lazyplan.db"
        self.path = profiles.path_for(self.db)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_legacy_value_loads_and_survives_a_save(self) -> None:
        self.path.write_text(
            json.dumps({"profiles": {"qa": {"tier": "deep", "effort": "ultra"}}}),
            encoding="utf-8",
        )
        loaded = profiles.load(self.db)
        self.assertEqual(loaded["qa"].effort, "ultra")
        profiles.save(self.db, loaded, profiles.default_tiers())
        self.assertEqual(profiles.load(self.db)["qa"].effort, "ultra")


class SessionEffortTest(unittest.TestCase):
    def test_the_wizard_accepts_only_curated_levels(self) -> None:
        session = setup.SetupSession(
            cwd=Path("."),
            home=Path("."),
            version="1.0",
            root=None,
            state=setup.SetupState(),
            draft=setup.SetupDraft(profiles_map=profiles.defaults()),
        )
        session.set_role_effort("qa", "inherit")
        self.assertEqual(session.draft.profiles_map["qa"].effort, "")
        session.set_role_effort("qa", "high")
        self.assertEqual(session.draft.profiles_map["qa"].effort, "high")
        with self.assertRaises(setup.SetupSessionError):
            session.set_role_effort("qa", "turbo")
