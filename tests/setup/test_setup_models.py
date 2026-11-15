"""Setup seeds and migrates the host-agnostic model map."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lazyplan.presentation import setup


class ProfileMapSetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
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


if __name__ == "__main__":
    unittest.main()
