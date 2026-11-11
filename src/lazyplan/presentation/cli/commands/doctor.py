"""Doctor CLI command."""

from __future__ import annotations

import argparse
from pathlib import Path

from lazyplan.infrastructure.repo import find_repo_root
from lazyplan.presentation import setup
from lazyplan.services import hooks as hook_service

from ...setup import layout as setup_layout
from ..emit import _emit
from ..parser import package_version
from ..store import optional_store


def _doctor_data(
    args: argparse.Namespace, home: Path, state: setup.SetupState
) -> tuple[setup_layout.SetupLayout, list[Path], dict]:
    choice = setup.choice_from_args(args, Path.cwd(), home, state)
    root = find_repo_root(Path.cwd())
    layout, skill_files = setup.preview(choice, root, home)
    report = setup_layout.inventory(layout)
    report["findings"] = [
        {"kind": f.kind, "path": str(f.path), "state": f.state, "detail": f.detail}
        for f in setup.detect_findings(Path.cwd(), home, state)
    ]
    missing_hooks = [path for path in state.hook_files if not Path(path).is_file()]
    report["hooks"] = {
        "enabled": state.hooks,
        "mode": state.effective_mode(),
        "files": list(state.hook_files),
        "missing": missing_hooks,
    }
    report["state"] = state.to_dict()
    report["skills"] = [str(path) for path in skill_files]
    report["hook_probe"] = hook_service.probe(optional_store(args), Path.cwd())
    inspection = setup.inspect(choice, state, root, home, package_version())
    report["pending_integrations"] = [item.to_dict() for item in inspection.pending]
    issues = bool(report["findings"]) or bool(missing_hooks)
    issues = issues or bool(report["pending_integrations"])
    issues = issues or (state.hooks and not state.hook_files)
    issues = issues or state.version != setup.SETUP_VERSION
    report["clean"] = bool(report["clean"] and not issues)
    return layout, skill_files, report


def _print_doctor(layout: setup_layout.SetupLayout, skill_files: list[Path], report: dict) -> None:
    print(f"database:  {layout.db}")
    print(f"templates: {layout.templates_dir}")
    print(f"config:    {layout.config or '-'}")
    for skill in skill_files:
        print(f"skill:     {skill}")
    hooks = report["hooks"]
    print(f"hooks:     {hooks['mode'] if hooks['enabled'] else 'none'}")
    for path in hooks["files"]:
        print(f"hook:      {path}")
    probe = report["hook_probe"]
    print(f"hook check:{' ok' if probe['ok'] else ' ' + str(probe['reason'])}")
    for path in hooks["missing"]:
        print(f"hook miss: {path}")
    print(f"clean:     {'yes' if report['clean'] else 'no'}")
    for item in report["misplaced"]:
        print(f"misplaced: {item}")
    for item in report["missing"]:
        print(f"missing:   {item}")
    for finding in report["findings"]:
        print(f"finding:   {finding['kind']} {finding['path']} ({finding['state']})")
    for item in report["pending_integrations"]:
        print(f"pending:   {item['label']} ({item['id']})")
    for note in report["notes"]:
        print(f"note:      {note}")


def _cmd_doctor(store: object | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only setup report; never opens or writes a database."""
    del store, actor
    home = Path.home()
    state = setup.load_state(home)
    layout, skill_files, report = _doctor_data(args, home, state)
    code = 0 if report["clean"] else 1
    if getattr(args, "json", False):
        _emit(args, report)
        return code
    _print_doctor(layout, skill_files, report)
    return code
