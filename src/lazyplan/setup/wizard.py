"""Setup wizard."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .. import hook_install, skills
from ..repo import (
    find_repo_root,
    repo_plan_db_path,
)
from . import ui
from .constants import (
    HOME,
    NO_SETUP_ENV,
    REPO,
    SKIP_COMMANDS,
)
from .findings import _parse_agents, preview
from .layout import SetupChoice
from .state import SetupState, state_path


def run_wizard(
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    read: Any = None,
    write: Any = None,
    json_mode: bool = False,
    initial: SetupChoice | None = None,
    hooks_enabled: bool | None = None,
) -> dict[str, Any] | None:
    """Ask placement and agents, review, then apply. None means cancelled."""
    read = read or (lambda: input(""))
    write = write or sys.stderr
    color = ui.color_enabled(write, json_mode)
    try:
        return _run_wizard(cwd, home, state, version, read, write, color, initial, hooks_enabled)
    except (EOFError, KeyboardInterrupt):
        ui.note(write, "Setup cancelled; nothing was written.", color, "warn")
        return None


def _run_wizard(
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    read: Any,
    write: Any,
    color: bool,
    initial: SetupChoice | None,
    hooks_enabled: bool | None,
) -> dict[str, Any] | None:
    root = find_repo_root(cwd)
    ui.banner(write, color, version)
    repo_db = repo_plan_db_path(root) if root is not None else None
    seeded = initial or SetupChoice()
    default_placement = seeded.placement
    if default_placement not in (HOME, REPO):
        default_placement = REPO if repo_db is not None and repo_db.is_file() else state.placement
    if default_placement not in (HOME, REPO):
        default_placement = HOME
    placement = ui.ask_placement(write, read, root, home, default_placement, color)
    base_agents = seeded.agents if seeded.agents is not None else state.agents
    choice = SetupChoice(
        placement=placement,
        agents=base_agents or _parse_agents("", home),
        skills_dir=seeded.skills_dir or state.skills_dir or None,
        no_skills=seeded.no_skills,
    )
    hosts = skills.detect_agents(home)
    selected = ui.ask_agents(write, read, hosts, list(choice.agents or []), color)
    choice = SetupChoice(
        placement=placement,
        agents=selected,
        skills_dir=choice.skills_dir,
        no_skills=choice.no_skills,
    )
    layout, skill_files = preview(choice, root, home)
    labels = {host.key: host.label for host in hosts}
    plugins = (
        []
        if hooks_enabled is False
        else [
            (labels.get(spec.host, spec.host), spec.path)
            for spec in hook_install.preview(home, selected)
        ]
    )
    ui.render_review(
        write,
        layout.db,
        layout.templates_dir,
        skill_files,
        state_path(home),
        layout.config,
        color,
        plugins,
    )
    if not ui.confirm(write, read, color):
        ui.note(write, "Setup cancelled; nothing was written.", color, "warn")
        return None
    from .apply import apply_choice

    result = apply_choice(choice, root, home, version, write)
    result["wizard"] = True
    return result


def _setup_skipped(cmd: str | None, args: Any) -> bool:
    if os.environ.get(NO_SETUP_ENV, "").strip():
        return True
    return cmd in SKIP_COMMANDS or bool(getattr(args, "version", False))


def _explicit_db(args: Any) -> str | None:
    return str(getattr(args, "db", "") or os.environ.get("LAZYPLAN_DB", "") or "") or None


def _prompt_allowed(args: Any, interactive: bool | None) -> bool:
    if getattr(args, "json", False) or getattr(args, "yes", False):
        return False
    return ui.stdin_tty() and sys.stderr.isatty() if interactive is None else interactive
