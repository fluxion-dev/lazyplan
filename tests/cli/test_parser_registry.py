"""Parser noun groups stay covered by the surface registry."""

from __future__ import annotations

import unittest

from lazyplan.presentation.cli.parser import build_parser
from lazyplan.presentation.cli.parser.registry_groups import cli_group_actions
from tests.ia.test_surface_parity import cli_inventory


class ParserRegistryTest(unittest.TestCase):
    def test_registry_verbs_resolve_to_parser_actions(self) -> None:
        _root, groups, positional = cli_inventory()
        for noun, verbs in cli_group_actions().items():
            actions = groups.get(noun) or positional.get(noun) or set()
            for verb in verbs:
                with self.subTest(noun=noun, verb=verb):
                    self.assertIn(verb, actions)

    def test_every_core_group_exists(self) -> None:
        root = build_parser()
        sub = next(a for a in root._actions if hasattr(a, "choices") and a.choices)
        for noun in cli_group_actions():
            with self.subTest(noun=noun):
                self.assertIn(noun, sub.choices)


if __name__ == "__main__":
    unittest.main()
