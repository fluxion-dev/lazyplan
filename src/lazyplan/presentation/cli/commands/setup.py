"""Setup CLI command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lazyplan.infrastructure.repo import find_repo_root
from lazyplan.presentation import setup

from ...setup import ui as setup_ui
from ..emit import _emit
from ..parser import package_version


def _setup_interactive(args: argparse.Namespace) -> bool:
    return (
        not getattr(args, "yes", False)
        and not getattr(args, "json", False)
        and not getattr(args, "post_upgrade", False)
        and setup_ui.stdin_tty()
        and sys.stderr.isatty()
    )


def _setup_review(args: argparse.Namespace, home: Path, interactive: bool) -> None:
    findings = setup.detect_findings(Path.cwd(), home, setup.load_state(home))
    if not findings:
        return
    ask = (
        not getattr(args, "json", False)
        and setup_ui.stdin_tty()
        and sys.stderr.isatty()
        and (interactive or bool(getattr(args, "post_upgrade", False)))
    )
    setup.review_findings(
        findings,
        setup.load_state(home),
        home,
        find_repo_root(Path.cwd()),
        read=input,
        write=sys.stderr,
        color=setup_ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
        allow_prompt=ask,
        json_mode=bool(getattr(args, "json", False)),
    )


def _print_setup(result: dict) -> None:
    print(f"database:  {result['db']}")
    print(f"templates: {result['templates']}")
    if result["config"]:
        print(f"config:    {result['config']}")
    for skill in result["skills"]:
        print(f"skill:     {skill}")
    for path in result["refreshed"]:
        print(f"refreshed: {path}")
    for path in result.get("backups") or []:
        print(f"backup:    {path}")
    hooks = result.get("hooks") or {}
    for path in hooks.get("installed") or hooks.get("removed") or []:
        print(f"hooks:     {path}")
    for item in hooks.get("skipped") or []:
        print(f"hooks:     skipped {item['path']} ({item['reason']})")
    pointer = result.get("agents_pointer") or {}
    if pointer.get("path"):
        print(f"pointer:   {pointer['path']} ({pointer['status']})")
    review = result.get("integration_review") or {}
    for path in review.get("installed") or []:
        print(f"integration: {path}")
    for item in review.get("pending") or []:
        print(f"pending:   {item.get('label', item.get('id', '?'))}")
    print(f"state:     {result['state']}")


def _cmd_setup(store: object | None, args: argparse.Namespace, actor: str) -> int:
    """Re-run setup, or apply remembered choices without prompts."""
    from lazyplan.infrastructure import hook_install

    del store, actor
    home = Path.home()
    state = setup.load_state(home)
    version = package_version()
    interactive = _setup_interactive(args)
    root = find_repo_root(Path.cwd())
    choice = setup.choice_from_args(args, Path.cwd(), home, state)
    if interactive:
        result = setup.run_wizard(
            Path.cwd(),
            home,
            state,
            version,
            initial=choice,
            hooks_enabled=getattr(args, "hooks", None),
        )
        if result is None:
            return _emit(args, {"cancelled": True}) if getattr(args, "json", False) else 0
    else:
        result = setup.apply_choice(choice, root, home, version)
    if getattr(args, "post_upgrade", False):
        state = setup.load_state(home)
        choice = setup.choice_from_state(state)
        can_review = (
            not getattr(args, "json", False) and setup_ui.stdin_tty() and sys.stderr.isatty()
        )
        setup.refresh_integrations(
            result,
            choice,
            home,
            root,
            version,
            read=input,
            write=sys.stderr,
            color=setup_ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
            allow_prompt=can_review,
            pointer_mode=getattr(args, "agents_pointer", None),
        )
    else:
        setup.install_integrations(
            result,
            home,
            root,
            getattr(args, "hooks", None),
            getattr(args, "agents_pointer", None),
        )
        state = setup.load_state(home)
        choice = setup.choice_from_state(state)
        inspection = setup.inspect(choice, state, root, home, version)
        if setup.remember_installed(inspection, state, version):
            setup.save_state(state, home)
        review = setup.review_pending(
            choice,
            state,
            root,
            home,
            version,
            read=input,
            write=sys.stderr,
            color=setup_ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
            allow_prompt=interactive,
        )
        result["integration_review"] = review.to_dict()
    if result.get("placement") == setup.HOME:
        _setup_review(args, home, interactive)
    if result.get("wizard") and not getattr(args, "json", False):
        selected = [h for h in (result.get("agents") or []) if h in hook_install.HOSTS]
        plugins = (
            [spec.path for spec in hook_install.preview(home, selected)]
            if getattr(args, "hooks", None) is not False
            else []
        )
        backups = [Path(path) for path in result.get("hooks", {}).get("backups") or []]
        setup_ui.success(
            sys.stderr,
            Path(result["db"]),
            [Path(path) for path in result["skills"]],
            backups,
            setup_ui.color_enabled(sys.stderr, False),
            plugins,
        )
        return 0
    if getattr(args, "json", False):
        return _emit(args, result)
    _print_setup(result)
    return 0
