"""Cross-surface parity: every action resolves to a CLI path and MCP tool."""

from __future__ import annotations

import argparse
import unittest

from lazyplan.presentation.cli.parser import build_parser
from lazyplan.presentation.mcp.registry_tools import tool_actions, tool_labels
from lazyplan.presentation.mcp.server import McpServer
from lazyplan.presentation.shared import registry


def _subparser(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))


def cli_inventory() -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    """Root commands, noun-group actions, and root positional actions."""
    root_parser = build_parser()
    root = set(_subparser(root_parser).choices)
    groups: dict[str, set[str]] = {}
    positional: dict[str, set[str]] = {}
    for name, parser in _subparser(root_parser).choices.items():
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if subs:
            groups[name] = set(_subparser(parser).choices)
            continue
        for action in parser._actions:
            if action.dest == "action" and action.choices:
                positional[name] = set(action.choices)
    return root, groups, positional


def cli_path_exists(path: str) -> bool:
    """True when the parser accepts this canonical noun-first path."""
    root, groups, positional = cli_inventory()
    parts = path.split()
    if len(parts) == 1:
        return parts[0] in root
    if parts[0] in groups:
        return parts[1] in groups[parts[0]]
    if parts[0] in positional:
        return parts[1] in positional[parts[0]]
    return False


class SurfaceParityTest(unittest.TestCase):
    def test_every_declared_surface_has_a_path_or_exception(self) -> None:
        self.assertEqual(registry.uncovered(registry.ACTIONS), [])

    def test_every_cli_mapping_resolves_to_a_parser_path(self) -> None:
        for action_id, paths in registry.CLI_ACTIONS.items():
            with self.subTest(action=action_id):
                self.assertTrue(paths)
                for path in paths:
                    self.assertTrue(cli_path_exists(path), path)

    def test_every_mcp_mapping_resolves_to_a_tool(self) -> None:
        tools = {item["name"] for item in McpServer(None).tools()}
        for action_id, tool in registry.MCP_ACTIONS.items():
            with self.subTest(action=action_id):
                self.assertIn(tool, tools)

    def test_registry_tools_resolve_to_live_tools(self) -> None:
        tools = {item["name"] for item in McpServer(None).tools()}
        for tool in tool_actions().values():
            with self.subTest(tool=tool):
                self.assertIn(tool, tools)

    def test_every_registry_tool_has_a_label(self) -> None:
        for tool, label in tool_labels().items():
            with self.subTest(tool=tool):
                self.assertTrue(label.strip())

    def test_mappings_only_cover_declared_surfaces(self) -> None:
        by_id = {action.id: action for action in registry.ACTIONS}
        for action_id in registry.CLI_ACTIONS:
            self.assertIn("cli", by_id[action_id].surfaces, action_id)
        for action_id in registry.MCP_ACTIONS:
            self.assertIn("mcp", by_id[action_id].surfaces, action_id)

    def test_every_exception_is_approved_and_explained(self) -> None:
        by_id = {action.id: action for action in registry.ACTIONS}
        for row in registry.SURFACE_EXCEPTIONS:
            with self.subTest(action=row.action, surface=row.surface):
                self.assertIn(row.action, by_id)
                self.assertIn(row.surface, registry.SURFACES)
                self.assertNotIn(row.surface, by_id[row.action].surfaces)
                self.assertTrue(row.reason.strip())

    def test_a_deliberate_gap_fails(self) -> None:
        gap = registry.Action(
            "plan.gap",
            "Deliberate gap",
            surfaces=("tui", "cli", "mcp"),
            route=("tree", "gap"),
        )
        errors = registry.uncovered((gap,))
        self.assertEqual(len(errors), 2)
        self.assertIn("plan.gap: cli", errors)
        self.assertIn("plan.gap: mcp", errors)

    def test_read_only_mcp_omits_write_tools(self) -> None:
        full = {item["name"]: item for item in McpServer(None).tools()}
        read_only = {item["name"]: item for item in McpServer(None, read_only=True).tools()}
        self.assertTrue(set(read_only) < set(full))
        for name, definition in read_only.items():
            with self.subTest(tool=name):
                self.assertTrue(definition["annotations"]["readOnlyHint"])

    def test_every_entity_has_at_least_one_action(self) -> None:
        report = registry.reachability_report()
        for entity in registry.ENTITIES:
            with self.subTest(entity=entity):
                self.assertIsNotNone(report["entities"][entity])


if __name__ == "__main__":
    unittest.main()
