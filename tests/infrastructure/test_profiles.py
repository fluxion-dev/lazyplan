"""Agent profile map: defaults, overrides, host resolution, and errors."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from lazyplan.core.policies.lanes import AGENT_ROLES
from lazyplan.infrastructure import profiles


class ProfileMapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")
        self.path = profiles.path_for(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_packaged_defaults_cover_every_role(self) -> None:
        loaded = profiles.defaults()
        self.assertEqual(set(loaded), set(AGENT_ROLES))
        self.assertEqual(loaded["implementer"].tier, "fast")
        self.assertEqual(loaded["reviewer"].tier, "deep")

    def test_missing_file_keeps_the_defaults(self) -> None:
        self.assertEqual(profiles.load(self.db), profiles.defaults())

    def test_partial_file_merges_with_defaults(self) -> None:
        self._write(
            {
                "profiles": {
                    "implementer": {"tier": "standard", "model": "fast/model", "effort": "low"}
                }
            }
        )
        loaded = profiles.load(self.db)
        self.assertEqual(loaded["implementer"].model, "fast/model")
        self.assertEqual(loaded["implementer"].effort, "low")
        self.assertEqual(loaded["reviewer"].tier, "deep")

    def test_resolution_uses_host_tiers(self) -> None:
        profile = profiles.Profile(role="implementer", tier="fast")
        self.assertEqual(profiles.resolve(profile, "claude")["model"], "haiku")
        self.assertEqual(
            profiles.resolve(profile, "opencode", {"main": "big", "small": "tiny"})["model"],
            "tiny",
        )
        self.assertEqual(
            profiles.resolve(
                profiles.Profile(role="implementer", tier="deep"),
                "opencode",
                {"main": "big", "small": "tiny"},
            )["model"],
            "big",
        )
        self.assertEqual(profiles.resolve(profile, "codex")["model"], "")

    def test_explicit_model_wins_on_every_host(self) -> None:
        profile = profiles.Profile(role="qa", tier="deep", model="provider/model")
        self.assertEqual(profiles.resolve(profile, "claude")["model"], "provider/model")

    def test_unknown_role_field_and_tier_are_rejected(self) -> None:
        cases = (
            {"profiles": {"wizard": {"tier": "fast"}}},
            {"profiles": {"qa": {"tier": "fast", "colour": "red"}}},
            {"profiles": {"qa": {"tier": "turbo"}}},
            {"profiles": []},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self._write(payload)
                with self.assertRaises(profiles.ProfileError):
                    profiles.load(self.db)

    def test_malformed_json_names_the_file(self) -> None:
        Path(self.path).write_text("{nope", encoding="utf-8")
        with self.assertRaisesRegex(profiles.ProfileError, "invalid JSON"):
            profiles.load(self.db)

    def test_dispatch_profiles_resolve_each_host(self) -> None:
        payload = profiles.dispatch_profiles(self.db)
        self.assertEqual(payload["implementer"]["tier"], "fast")
        self.assertEqual(payload["implementer"]["claude"], "haiku")
        self.assertEqual(payload["reviewer"]["claude"], "opus")


if __name__ == "__main__":
    unittest.main()
