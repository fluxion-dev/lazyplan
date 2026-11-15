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
        tiers = profiles.default_tiers()
        self.assertEqual(tiers["fast"]["claude"], "haiku")
        self.assertEqual(tiers["deep"]["claude"], "opus")

    def test_missing_file_keeps_the_defaults(self) -> None:
        self.assertEqual(profiles.load(self.db), profiles.defaults())
        self.assertEqual(profiles.load_all(self.db)[1], profiles.default_tiers())

    def test_v1_file_migrates_to_schema_two(self) -> None:
        self._write(
            {
                "profiles": {
                    "implementer": {"tier": "fast", "model": "provider/small", "effort": "low"}
                }
            }
        )
        loaded = profiles.load(self.db)
        self.assertEqual(loaded["implementer"].model, "provider/small")
        profiles.save(self.db, loaded, profiles.load_all(self.db)[1])
        written = json.loads(Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(written["schema"], 2)
        self.assertEqual(written["profiles"]["implementer"]["model"], "provider/small")
        self.assertEqual(written["tiers"]["fast"]["claude"], "haiku")

    def test_tier_and_per_host_overrides_resolve_in_order(self) -> None:
        loaded = {
            "qa": profiles.Profile(
                role="qa",
                tier="deep",
                model="all/host",
                models={"claude": "claude/role"},
            )
        }
        tiers = {"deep": {"claude": "claude/tier", "opencode": "tier/model"}}
        self.assertEqual(
            profiles.resolve(loaded["qa"], "claude", tiers=tiers)["model"],
            "claude/role",
        )
        self.assertEqual(
            profiles.resolve(loaded["qa"], "opencode", tiers=tiers)["model"],
            "all/host",
        )
        plain = {"qa": profiles.Profile(role="qa", tier="deep")}
        self.assertEqual(
            profiles.resolve(plain["qa"], "opencode", tiers=tiers)["model"],
            "tier/model",
        )
        self.assertEqual(
            profiles.resolve(plain["qa"], "codex", tiers=tiers)["model"],
            "",
        )

    def test_unknown_top_level_tier_and_host_are_rejected(self) -> None:
        cases = (
            {"profiles": {}, "extra": True},
            {"profiles": {}, "tiers": {"turbo": {"claude": "x"}}},
            {"profiles": {}, "tiers": {"fast": {"wizard": "x"}}},
            {"profiles": {"qa": {"tier": "fast", "models": {"wizard": "x"}}}},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self._write(payload)
                with self.assertRaises(profiles.ProfileError):
                    profiles.load(self.db)

    def test_save_is_idempotent_and_keeps_every_host(self) -> None:
        loaded, tiers = profiles.load_all(self.db)
        profiles.save(self.db, loaded, tiers)
        first = Path(self.path).read_text(encoding="utf-8")
        profiles.save(self.db, loaded, tiers)
        self.assertEqual(Path(self.path).read_text(encoding="utf-8"), first)
        written = json.loads(first)
        for tier in profiles.TIERS:
            self.assertEqual(set(written["tiers"][tier]), set(profiles.HOSTS))

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

    def test_resolve_all_covers_every_host(self) -> None:
        loaded = profiles.defaults()
        tiers = profiles.default_tiers()
        payload = profiles.resolve_all(loaded, tiers)
        self.assertEqual(set(payload), set(AGENT_ROLES))
        for resolved in payload.values():
            self.assertEqual(set(resolved["models"]), set(profiles.HOSTS))
            for host in profiles.HOSTS:
                self.assertEqual(resolved[host], resolved["models"][host])
        self.assertEqual(payload["implementer"]["opencode"], "")
        self.assertEqual(payload["implementer"]["claude"], "haiku")

    def test_resolve_rejects_unknown_host(self) -> None:
        with self.assertRaisesRegex(profiles.ProfileError, "unknown host"):
            profiles.resolve(profiles.Profile(role="qa"), "wizard")

    def test_per_host_override_wins_over_all_host_and_tier(self) -> None:
        profile = profiles.Profile(
            role="reviewer",
            tier="deep",
            model="all/host",
            models={"codex": "codex/role"},
        )
        tiers = {"deep": {"codex": "codex/tier", "claude": "opus"}}
        self.assertEqual(profiles.resolve(profile, "codex", tiers=tiers)["model"], "codex/role")
        self.assertEqual(profiles.resolve(profile, "claude", tiers=tiers)["model"], "all/host")
        plain = profiles.Profile(role="reviewer", tier="deep")
        self.assertEqual(profiles.resolve(plain, "codex", tiers=tiers)["model"], "codex/tier")
        self.assertEqual(profiles.resolve(plain, "gemini", tiers=tiers)["model"], "")


if __name__ == "__main__":
    unittest.main()
