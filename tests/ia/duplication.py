"""Duplication inventory for the CLI, MCP, and palette adapters.

One row per declared action shows where it is reachable and which handler
serves it, so a surface change can be checked against the registry instead of
grep. The duplicate detectors compare normalized shapes, not names, so two
builders that differ only in strings still count as one wiring written twice.
"""

from __future__ import annotations

import ast
from pathlib import Path

from lazyplan.presentation.shared import registry
from lazyplan.presentation.shared.registry_surfaces import CLI_ACTIONS, MCP_ACTIONS
from tests.support.paths import ROOT

PRESENTATION = ROOT / "src" / "lazyplan" / "presentation"
PARSER_DIR = PRESENTATION / "cli" / "parser"
MCP_DIR = PRESENTATION / "mcp"
SHARED_DIR = PRESENTATION / "shared"

#: Registry modules that hold the canonical ``Action`` rows.
ACTION_ROW_MODULES = frozenset(
    {"registry_actions.py", "registry_actions_provenance.py", "registry_actions_drafts.py"}
)

#: Keyword arguments that shape how a flag parses; help text and metavar names
#: are presentation, not wiring.
WIRING_KEYS = ("type", "required", "action", "choices", "default", "nargs")


def surface_rows() -> list[dict[str, object]]:
    """One row per action: CLI path, MCP tool, palette command, and handler."""
    rows: list[dict[str, object]] = []
    for action in sorted(registry.ACTIONS, key=lambda item: item.id):
        commands = [cmd for cmd in registry.COMMANDS if cmd.action_id == action.id]
        rows.append(
            {
                "action": action.id,
                "cli": " ".join(CLI_ACTIONS.get(action.id, ())),
                "mcp": MCP_ACTIONS.get(action.id, ""),
                "palette": " ".join(cmd.id for cmd in commands),
                "handlers": " ".join(cmd.handler for cmd in commands if cmd.handler),
            }
        )
    return rows


def _normalized_call(call: ast.Call) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    """One builder call as (method, flag, kept keyword shapes).

    The flag name distinguishes ``--read-only`` from ``--check``; the
    subcommand name does not, because two names sharing one flag set is
    exactly the duplication this detector reports.
    """
    method = call.func.attr if isinstance(call.func, ast.Attribute) else ""
    first = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else ""
    flag = str(first) if method == "add_argument" else ""
    kept = sorted(
        (kw.arg, ast.dump(kw.value, annotate_fields=False))
        for kw in call.keywords
        if kw.arg in WIRING_KEYS
    )
    return method, flag, tuple(kept)


def _wiring(node: ast.FunctionDef) -> tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...]:
    """The parser-building calls inside one ``add_*`` function, in order."""
    calls = []
    for statement in ast.walk(node):
        if isinstance(statement, ast.Call) and isinstance(statement.func, ast.Attribute):
            if statement.func.attr in ("add_argument", "add_parser"):
                calls.append(_normalized_call(statement))
    return tuple(calls)


def parser_duplicates(root: Path = PARSER_DIR) -> list[tuple[str, ...]]:
    """``add_*`` builders that wire the same flags, one sorted group each.

    A builder that only names a subcommand carries no flag wiring to share, so
    it is not compared; only builders that declare at least one argument are.
    """
    by_wiring: dict[tuple[object, ...], list[str]] = {}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("add_"):
                continue
            calls = _wiring(node)
            if any(method == "add_argument" for method, _, _ in calls):
                by_wiring.setdefault(calls, []).append(f"{path.stem}:{node.name}")
    return sorted(tuple(sorted(names)) for names in by_wiring.values() if len(names) > 1)


class _Shape(ast.NodeTransformer):
    """Erase names, attributes, and string constants from a handler body."""

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id="_", ctx=node.ctx), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        node.attr = "_"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value=None), node)
        return node


def handler_duplicates(root: Path = MCP_DIR) -> list[tuple[str, ...]]:
    """MCP ``_tool_*`` handlers with identical normalized bodies, per group."""
    import hashlib

    by_body: dict[str, list[str]] = {}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("_tool_"):
                continue
            body = [
                statement
                for statement in node.body
                if not (
                    isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                )
            ]
            shaped = [_Shape().visit(statement) for statement in body]
            dump = ast.dump(ast.Module(body=shaped, type_ignores=[]), annotate_fields=False)
            by_body.setdefault(hashlib.sha1(dump.encode()).hexdigest(), []).append(
                f"{path.stem}:{node.name}"
            )
    return sorted(tuple(sorted(names)) for names in by_body.values() if len(names) > 1)


def retyped_actions(root: Path = SHARED_DIR) -> dict[str, int]:
    """Action ids typed as string literals outside the ``Action`` rows."""
    declared = {action.id for action in registry.ACTIONS}
    found: dict[str, int] = {}
    for path in sorted(root.glob("registry_*.py")):
        if path.name in ACTION_ROW_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in declared
            ):
                found[node.value] = found.get(node.value, 0) + 1
    return found


def render() -> str:
    """The full report as Markdown, one section per detector."""
    lines = ["# Adapter duplication report", ""]
    lines.append("| action | cli | mcp | palette | handlers |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in surface_rows():
        lines.append(
            f"| {row['action']} | {row['cli']} | {row['mcp']} | {row['palette']} |"
            f" {row['handlers']} |"
        )
    lines.append("")
    lines.append("## Parser builders that share wiring")
    for group in parser_duplicates():
        lines.append(f"- {' '.join(group)}")
    lines.append("")
    lines.append("## MCP handlers that share a body")
    for group in handler_duplicates():
        lines.append(f"- {' '.join(group)}")
    lines.append("")
    retyped = retyped_actions()
    lines.append(
        f"## Action ids typed outside the Action rows: {len(retyped)} ids,"
        f" {sum(retyped.values())} occurrences"
    )
    return "\n".join(lines) + "\n"
