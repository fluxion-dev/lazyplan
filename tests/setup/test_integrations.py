"""Integration catalog: stable IDs, fingerprints, and resolved targets."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lazyplan.infrastructure import hook_hosts, hook_install, integrations, skills


class CatalogCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.items = {item.id: item for item in integrations.catalog(self.home)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_ids_are_unique_and_stable(self):
        items = integrations.catalog(self.home)
        ids = [item.id for item in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "skill:lazyplan")
        self.assertIn("hook:opencode:plugin", ids)

    def test_catalog_names_every_skill_and_hook_event(self):
        self.assertEqual(
            {
                item.id
                for item in integrations.catalog(self.home)
                if item.kind == integrations.SKILL
            },
            {f"skill:{spec.name}" for spec in skills.SKILLS},
        )
        expected = {f"hook:opencode:{integrations.PLUGIN_EVENT}"}
        for host in hook_install.HOSTS:
            if host == "opencode":
                continue
            expected.update(f"hook:{host}:{event}" for event in hook_hosts.EVENTS[host])
        actual = {
            item.id for item in integrations.catalog(self.home) if item.kind == integrations.HOOK
        }
        self.assertEqual(actual, expected)

    def test_skill_fingerprint_tracks_only_the_skill_body(self):
        before = dict(self.items)
        with mock.patch.object(skills, "render_skill", return_value="changed"):
            after = {item.id: item for item in integrations.catalog(self.home)}
        self.assertNotEqual(
            before["skill:lazyplan"].fingerprint, after["skill:lazyplan"].fingerprint
        )
        self.assertEqual(
            before["hook:claude:session-start"].fingerprint,
            after["hook:claude:session-start"].fingerprint,
        )

    def test_hook_fingerprint_tracks_only_the_changed_event(self):
        before = dict(self.items)
        with mock.patch.dict(hook_hosts.EVENTS["claude"], {"session-start": "SessionStartX"}):
            after = {item.id: item for item in integrations.catalog(self.home)}
        self.assertNotEqual(
            before["hook:claude:session-start"].fingerprint,
            after["hook:claude:session-start"].fingerprint,
        )
        self.assertEqual(
            before["hook:claude:stop"].fingerprint,
            after["hook:claude:stop"].fingerprint,
        )

    def test_hook_fingerprint_tracks_a_matcher_change(self):
        before = dict(self.items)
        with mock.patch.dict(hook_hosts.MATCHERS["claude"], {"PostToolUse": "Edit"}):
            after = {item.id: item for item in integrations.catalog(self.home)}
        self.assertNotEqual(
            before["hook:claude:post-tool"].fingerprint,
            after["hook:claude:post-tool"].fingerprint,
        )
        self.assertEqual(
            before["hook:claude:pre-tool"].fingerprint,
            after["hook:claude:pre-tool"].fingerprint,
        )

    def test_adding_a_hook_event_leaves_existing_fingerprints_alone(self):
        before = dict(self.items)
        with mock.patch.dict(hook_hosts.EVENTS["claude"], {"session-end": "SessionEnd"}):
            after = {item.id: item for item in integrations.catalog(self.home)}
        self.assertIn("hook:claude:session-end", after)
        for key, item in before.items():
            self.assertEqual(item.fingerprint, after[key].fingerprint)

    def test_hook_paths_resolve_host_surfaces(self):
        claude = self.items["hook:claude:session-start"]
        self.assertEqual(
            integrations.hook_paths(claude, self.home),
            [self.home / ".claude" / "settings.json"],
        )
        plugin = self.items["hook:opencode:plugin"]
        self.assertEqual(
            integrations.hook_paths(plugin, self.home),
            [self.home / ".config" / "opencode" / "plugins" / hook_install.PLUGIN_NAME],
        )
        self.assertEqual(integrations.hook_paths(self.items["skill:lazyplan"], self.home), [])

    def test_skill_paths_resolve_the_tool_directory(self):
        skill = self.items["skill:lazyplan"]
        expected = self.home / ".claude" / "skills" / "lazyplan" / "SKILL.md"
        self.assertEqual(
            integrations.skill_paths(
                skill,
                "global",
                None,
                home=self.home,
                tools=["claude"],
            ),
            [expected],
        )
        self.assertEqual(
            integrations.skill_paths(
                self.items["hook:claude:stop"],
                "global",
                None,
                home=self.home,
            ),
            [],
        )

    def test_to_dict_is_json_safe(self):
        payload = self.items["skill:lazyplan"].to_dict()
        self.assertEqual(payload["id"], "skill:lazyplan")
        self.assertEqual(payload["kind"], integrations.SKILL)
        self.assertEqual(payload["skill"], "lazyplan")
        self.assertEqual(payload["host"], "")


if __name__ == "__main__":
    unittest.main()
