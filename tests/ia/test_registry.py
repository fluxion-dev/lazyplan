"""The canonical registry rejects duplicates, key conflicts, and orphans."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from collections import Counter

from lazyplan.presentation.shared import registry
from lazyplan.presentation.shared.palette import COMMANDS
from tests.support.paths import ROOT


class TestRegistry(unittest.TestCase):
    def test_ids_are_unique_and_taxonomy_is_known(self):
        ids = [action.id for action in registry.ACTIONS]
        self.assertEqual([key for key, count in Counter(ids).items() if count > 1], [])
        for action in registry.ACTIONS:
            with self.subTest(action=action.id):
                self.assertIn(action.taxonomy, registry.TAXONOMY)

    def test_surfaces_and_routes_are_known_and_shallow(self):
        for action in registry.ACTIONS:
            with self.subTest(action=action.id):
                self.assertTrue(action.surfaces)
                self.assertTrue(set(action.surfaces) <= set(registry.SURFACES))
                self.assertLessEqual(len(action.route), 3)

    def test_no_key_is_bound_twice_in_one_context(self):
        seen: dict[tuple[str, str], str] = {}
        for action in registry.ACTIONS:
            if not action.key:
                continue
            key = (action.context, action.key)
            with self.subTest(context=action.context, key=action.key):
                self.assertNotIn(key, seen, f"{action.id} collides with {seen.get(key)}")
                seen[key] = action.id

    def test_every_palette_command_has_one_action(self):
        palette_ids = {command.id for command in COMMANDS}
        mapped = registry.PALETTE_TO_ACTION
        self.assertEqual(palette_ids - set(mapped), set())
        self.assertEqual(set(mapped) - palette_ids, set())

    def test_deprecations_name_a_removal(self):
        for action in registry.ACTIONS:
            if action.deprecated_in:
                self.assertTrue(action.removal, action.id)

    def test_registry_imports_without_textual(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        code = (
            "import sys; sys.path.insert(0, 'src'); "
            "from lazyplan.presentation.shared.registry import ACTIONS; print(len(ACTIONS))"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(int(result.stdout.strip()), 0)


if __name__ == "__main__":
    unittest.main()
