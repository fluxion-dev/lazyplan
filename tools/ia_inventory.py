#!/usr/bin/env python3
"""Information-architecture inventory for every lazyplan access path.

Emits Markdown for humans and JSON for tests. ``--check`` compares the live
registries with the committed snapshot. Stdlib only; never imports Textual.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SNAPSHOT_DIR = ROOT / "docs" / "information-architecture"
MARKDOWN = SNAPSHOT_DIR / "inventory.md"
JSON_FILE = SNAPSHOT_DIR / "inventory.json"
DOC_PATHS = (
    "README.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "docs/usage.md",
    "docs/lpui.1",
    "docs/lazyplan.1",
    "src/lazyplan/data/AGENTS.md",
    "src/lazyplan/data/SKILL.md",
    "site/index.html",
)


def _cli_report() -> dict[str, Any]:
    from lazyplan.presentation.cli.parser import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    commands = []
    for name in sorted(sub.choices):
        actions = []
        for action in sub.choices[name]._actions:
            if action.dest == "help":
                continue
            actions.append(sorted(action.option_strings))
        commands.append({"name": name, "options": actions})
    return {"count": len(commands), "commands": commands}


def _palette_report() -> dict[str, Any]:
    from lazyplan.presentation.shared.palette import COMMANDS

    rows = []
    for cmd in COMMANDS:
        rows.append(
            {
                "id": cmd.id,
                "label": cmd.label,
                "key": cmd.key or "",
                "handler": cmd.handler,
                "section": cmd.section,
                "help_group": cmd.help_group or "",
            }
        )
    rows.sort(key=lambda row: row["id"])
    return {"count": len(rows), "commands": rows}


def _mcp_report() -> dict[str, Any]:
    from lazyplan.presentation.mcp.server import McpServer

    server = McpServer(None)
    tools = sorted(
        (
            {"name": item["name"], "description": item.get("description", "")}
            for item in server.tools()
        ),
        key=lambda row: row["name"],
    )
    resources = sorted(
        ({"uri": item["uri"], "name": item["name"]} for item in server.resources()),
        key=lambda row: row["uri"],
    )
    return {"tools": tools, "resources": resources}


def _binding_calls(path: Path) -> list[dict[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != "Binding" or len(node.args) < 2:
            continue
        values = [arg.value for arg in node.args[:3] if isinstance(arg, ast.Constant)]
        if len(values) >= 2:
            out.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "screen": path.stem,
                    "line": str(node.lineno),
                    "key": str(values[0]),
                    "action": str(values[1]),
                    "label": str(values[2]) if len(values) > 2 else "",
                }
            )
    return out


def _tui_report() -> dict[str, Any]:
    tui = ROOT / "src" / "lazyplan" / "presentation" / "tui"
    screens = []
    for path in sorted(tui.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith("Screen"):
                screens.append({"file": path.relative_to(ROOT).as_posix(), "class": node.name})
    bindings: list[dict[str, str]] = []
    for path in sorted(tui.rglob("*.py")):
        bindings.extend(_binding_calls(path))
    bindings.sort(key=lambda row: (row["file"], row["key"], row["action"]))
    by_key: dict[str, list[dict[str, str]]] = {}
    for row in bindings:
        by_key.setdefault(row["key"], []).append(
            {"file": row["file"], "action": row["action"], "line": row["line"]}
        )
    conflicts = []
    for key, values in sorted(by_key.items()):
        unique = {(row["file"], row["action"], row["line"]) for row in values}
        if len(unique) > 1:
            conflicts.append(
                {
                    "key": key,
                    "bindings": [
                        {"file": file, "action": action, "line": line}
                        for file, action, line in sorted(unique)
                    ],
                }
            )
    return {"screens": screens, "bindings": bindings, "conflicts": conflicts}


def _setup_report() -> dict[str, Any]:
    path = ROOT / "src" / "lazyplan" / "presentation" / "setup" / "ui.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    steps = sorted(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("ask_")
    )
    return {"steps": steps}


def _hooks_report() -> dict[str, Any]:
    from lazyplan.infrastructure.hook_hosts import EVENTS

    rows = [
        {"host": host, "event": event, "native": native}
        for host, events in EVENTS.items()
        for event, native in events.items()
    ]
    rows.sort(key=lambda row: (row["host"], row["event"]))
    return {"events": rows}


def _metadata_report() -> dict[str, Any]:
    from lazyplan.infrastructure.docs_meta import ENVIRONMENT, FILES

    usage = (ROOT / "docs/usage.md").read_text(encoding="utf-8")
    man = (ROOT / "docs/lpui.1").read_text(encoding="utf-8").replace("\\-", "-").replace("\\.", ".")
    environment = [
        {
            "name": name,
            "in_usage": name.split(",")[0].strip() in usage,
            "in_man": name.split(",")[0].strip() in man,
        }
        for name, _text in ENVIRONMENT
    ]
    files = [
        {
            "name": name,
            "in_usage": name.split(",")[0].strip() in usage,
            "in_man": name.split(",")[0].strip() in man,
        }
        for name, _text in FILES
    ]
    return {"environment": environment, "files": files}


STALE_CLAIMS = (
    ("docs/design-system.md", "site/index.html design section"),
    ("src/lazyplan/design/", "src/lazyplan/presentation/shared/design/"),
    ("src/lazyplan/tui/", "src/lazyplan/presentation/tui/"),
    ("src/lazyplan/palette.py", "src/lazyplan/presentation/shared/palette.py"),
    ("`F` cycles source filters", "`f` cycles plan modes"),
    ("status filter", "plan mode"),
    ("needs me lens", "active plan mode"),
)


def _stale_report() -> dict[str, Any]:
    rows = []
    for stale, replacement in STALE_CLAIMS:
        found = []
        for name in DOC_PATHS:
            path = ROOT / name
            if not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if stale in line:
                    found.append({"file": name, "line": number})
        rows.append({"claim": stale, "replacement": replacement, "found": found})
    return {"claims": rows}


def _headings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        return [
            re.sub(r"<[^>]+>", "", match).strip()
            for match in re.findall(r"<h[12][^>]*>(.*?)</h[12]>", text, re.S | re.I)
        ]
    if path.suffix == ".1":
        return [match.strip() for match in re.findall(r"^\.SH (.+)$", text, re.M)]
    return [match.strip() for match in re.findall(r"^#{1,3} (.+)$", text, re.M)]


def _docs_report() -> dict[str, Any]:
    rows = []
    for name in DOC_PATHS:
        path = ROOT / name
        if path.is_file():
            rows.append({"file": name, "headings": _headings(path)})
    return {"files": rows}


def _registry_reports() -> dict[str, Any]:
    """Extract every registry through one seam for tests and refactors."""
    return {
        "cli": _cli_report(),
        "palette": _palette_report(),
        "mcp": _mcp_report(),
        "tui": _tui_report(),
        "setup": _setup_report(),
        "hooks": _hooks_report(),
        "docs": _docs_report(),
        "metadata": _metadata_report(),
        "stale": _stale_report(),
    }


def build_report() -> dict[str, Any]:
    """Collect every access-path surface from the live registries."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    surfaces = _registry_reports()
    cli = surfaces["cli"]
    palette = surfaces["palette"]
    mcp = surfaces["mcp"]
    tui = surfaces["tui"]
    setup = surfaces["setup"]
    hooks = surfaces["hooks"]
    docs = surfaces["docs"]
    metadata = surfaces["metadata"]
    stale = surfaces["stale"]
    counts = {
        "cli_commands": cli["count"],
        "palette_commands": palette["count"],
        "mcp_tools": len(mcp["tools"]),
        "mcp_resources": len(mcp["resources"]),
        "tui_screens": len(tui["screens"]),
        "tui_bindings": len(tui["bindings"]),
        "setup_steps": len(setup["steps"]),
        "hook_events": len(hooks["events"]),
        "doc_files": len(docs["files"]),
        "doc_headings": sum(len(row["headings"]) for row in docs["files"]),
        "tui_key_conflicts": len(tui["conflicts"]),
        "stale_claims": sum(len(row["found"]) for row in stale["claims"]),
        "env_names": len(metadata["environment"]),
        "file_paths": len(metadata["files"]),
    }
    return {
        "counts": counts,
        "cli": cli,
        "palette": palette,
        "mcp": mcp,
        "tui": tui,
        "setup": setup,
        "hooks": hooks,
        "docs": docs,
        "metadata": metadata,
        "stale": stale,
    }


def canonical_json(report: dict[str, Any]) -> str:
    """Stable snapshot text."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    """Human-readable inventory built from the same report."""
    lines = [
        "# Information architecture inventory",
        "",
        "Generated by `tools/ia_inventory.py`. Do not edit by hand; run",
        "`python3 tools/ia_inventory.py --write` after changing a surface.",
        "",
        "Ranked gaps live in [findings.md](findings.md). Regenerate and verify:",
        "",
        "```bash",
        "python3 tools/ia_inventory.py --write",
        "python3 tools/ia_inventory.py --check",
        "```",
        "",
        "## Counts",
        "",
        "| Surface | Count |",
        "| --- | ---: |",
    ]
    for name, value in report["counts"].items():
        lines.append(f"| {name} | {value} |")
    lines.extend(["", "## CLI commands", "", "| Command | Options |", "| --- | --- |"])
    for row in report["cli"]["commands"]:
        options = ", ".join(option for group in row["options"] for option in group)
        lines.append(f"| `{row['name']}` | {options} |")
    lines.extend(
        [
            "",
            "## Palette commands",
            "",
            "| ID | Label | Key | Handler |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in report["palette"]["commands"]:
        lines.append(f"| `{row['id']}` | {row['label']} | `{row['key']}` | `{row['handler']}` |")
    lines.extend(["", "## MCP tools", "", "| Tool | Description |", "| --- | --- |"])
    for row in report["mcp"]["tools"]:
        lines.append(f"| `{row['name']}` | {row['description']} |")
    lines.extend(["", "## MCP resources", "", "| URI | Name |", "| --- | --- |"])
    for row in report["mcp"]["resources"]:
        lines.append(f"| `{row['uri']}` | {row['name']} |")
    lines.extend(["", "## TUI screens", ""])
    lines.extend(f"- `{row['file']}` — {row['class']}" for row in report["tui"]["screens"])
    lines.extend(
        ["", "## TUI bindings", "", "| File | Key | Action | Label |", "| --- | --- | --- | --- |"]
    )
    for row in report["tui"]["bindings"]:
        lines.append(f"| `{row['file']}` | `{row['key']}` | `{row['action']}` | {row['label']} |")
    lines.extend(["", "## TUI key conflicts", "", "| Key | Files and actions |", "| --- | --- |"])
    for row in report["tui"]["conflicts"]:
        bindings = "; ".join(
            f"`{item['file']}:{item['line']}` → `{item['action']}`" for item in row["bindings"]
        )
        lines.append(f"| `{row['key']}` | {bindings} |")
    lines.extend(["", "## Setup steps", ""])
    lines.extend(f"- `{step}`" for step in report["setup"]["steps"])
    lines.extend(["", "## Hook events", "", "| Host | Event | Native |", "| --- | --- | --- |"])
    for row in report["hooks"]["events"]:
        lines.append(f"| {row['host']} | `{row['event']}` | `{row['native']}` |")
    lines.extend(
        ["", "## Environment and files", "", "| Name | In usage | In man |", "| --- | --- | --- |"]
    )
    for row in report["metadata"]["environment"] + report["metadata"]["files"]:
        lines.append(f"| `{row['name']}` | {row['in_usage']} | {row['in_man']} |")
    lines.extend(
        ["", "## Stale claims", "", "| Claim | Replacement | Found |", "| --- | --- | --- |"]
    )
    for row in report["stale"]["claims"]:
        found = ", ".join(f"`{item['file']}:{item['line']}`" for item in row["found"]) or "none"
        lines.append(f"| `{row['claim']}` | {row['replacement']} | {found} |")
    lines.extend(["", "## Documentation headings", "", "| File | Headings |", "| --- | --- |"])
    for row in report["docs"]["files"]:
        headings = " · ".join(row["headings"][:12])
        lines.append(f"| `{row['file']}` | {headings} |")
    return "\n".join(lines).rstrip() + "\n"


def snapshot_paths() -> tuple[Path, Path]:
    """The committed Markdown and JSON paths."""
    return MARKDOWN, JSON_FILE


def compare(report: dict[str, Any], markdown: str | None = None) -> list[str]:
    """Return snapshot differences for one live report."""
    errors: list[str] = []
    if not JSON_FILE.is_file():
        return [f"missing snapshot: {JSON_FILE.relative_to(ROOT)}"]
    if JSON_FILE.read_text(encoding="utf-8") != canonical_json(report):
        errors.append(f"stale snapshot: {JSON_FILE.relative_to(ROOT)}")
    if not MARKDOWN.is_file():
        errors.append(f"missing snapshot: {MARKDOWN.relative_to(ROOT)}")
    elif MARKDOWN.read_text(encoding="utf-8") != (markdown or render_markdown(report)):
        errors.append(f"stale snapshot: {MARKDOWN.relative_to(ROOT)}")
    return errors


def write_snapshot(report: dict[str, Any]) -> None:
    """Write both committed snapshots."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_FILE.write_text(canonical_json(report), encoding="utf-8")
    MARKDOWN.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Print the inventory, write it, or check the committed snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--write", action="store_true", help="refresh both snapshots")
    parser.add_argument("--check", action="store_true", help="fail when a snapshot is stale")
    args = parser.parse_args(argv)
    report = build_report()
    markdown = render_markdown(report)
    if args.write:
        write_snapshot(report)
        print(f"wrote {JSON_FILE.relative_to(ROOT)} and {MARKDOWN.relative_to(ROOT)}")
        return 0
    if args.check:
        errors = compare(report, markdown)
        if errors:
            print("inventory check failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print("inventory ok: every surface matches the snapshot")
        return 0
    print(canonical_json(report) if args.json else markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
