"""Agent catalog persistence and validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lazyplan.infrastructure.agents import (
    AgentProfile,
    catalog_path,
    default_profile,
    find_profile,
    load_catalog,
    save_catalog,
)


class TestAgentCatalog(unittest.TestCase):
    def test_missing_catalog_returns_opencode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles, default = load_catalog(tmp)
        self.assertEqual([profile.key for profile in profiles], ["opencode"])
        self.assertEqual(default, "opencode")
        self.assertEqual(profiles[0].command, ("opencode", "acp"))

    def test_save_and_reload_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles = [
                default_profile(),
                AgentProfile("claude", "Claude", ("claude-agent-acp",)),
            ]
            path = save_catalog(profiles, "claude", tmp)
            loaded, default = load_catalog(tmp)
            self.assertEqual(path, catalog_path(tmp))
            self.assertEqual([profile.key for profile in loaded], ["opencode", "claude"])
            self.assertEqual(default, "claude")
            self.assertEqual(find_profile("claude", tmp).title, "Claude")

    def test_unknown_default_falls_back_to_first_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = catalog_path(tmp)
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "default": "missing",
                        "agents": [{"key": "fake", "command": ["fake", "acp"]}],
                    }
                ),
                encoding="utf-8",
            )
            profiles, default = load_catalog(tmp)
        self.assertEqual([profile.key for profile in profiles], ["fake"])
        self.assertEqual(default, "fake")

    def test_bad_catalog_raises_a_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = catalog_path(tmp)
            path.parent.mkdir(parents=True)
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(tmp)

    def test_remove_keeps_a_valid_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profiles = [
                default_profile(),
                AgentProfile("claude", "Claude", ("claude-agent-acp",)),
            ]
            save_catalog(profiles, "opencode", tmp)
            remaining = [profile for profile in profiles if profile.key != "opencode"]
            save_catalog(remaining, remaining[0].key, tmp)
            loaded, default = load_catalog(tmp)
        self.assertEqual([profile.key for profile in loaded], ["claude"])
        self.assertEqual(default, "claude")

    def test_catalog_path_lives_in_the_shared_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(catalog_path(tmp), Path(tmp) / ".lazyplan" / "agents.json")


if __name__ == "__main__":
    unittest.main()
