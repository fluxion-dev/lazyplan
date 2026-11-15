"""Setup wizard."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from lazyplan.infrastructure import hook_install, host_models, skills
from lazyplan.infrastructure.repo import (
    find_repo_root,
    repo_plan_db_path,
)

from . import models, ui
from .constants import (
    HOME,
    NO_SETUP_ENV,
    REPO,
    SKIP_COMMANDS,
)
from .findings import parse_agents, preview
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
    hooks_mode: str | None = None,
) -> dict[str, Any] | None:
    """Ask placement and agents, review, then apply. None means cancelled."""
    read = read or (lambda: input(""))
    write = write or sys.stderr
    color = ui.color_enabled(write, json_mode)
    try:
        return run_wizard_flow(cwd, home, state, version, read, write, color, initial, hooks_mode)
    except (EOFError, KeyboardInterrupt):
        ui.note(write, "Setup cancelled; nothing was written.", color, "warn")
        return None


def run_wizard_flow(
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    read: Any,
    write: Any,
    color: bool,
    initial: SetupChoice | None,
    hooks_mode: str | None,
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
    choice = replace(
        seeded,
        placement=placement,
        agents=base_agents or parse_agents("", home),
        skills_dir=seeded.skills_dir or state.skills_dir or None,
    )
    hosts = skills.detect_agents(home)
    selected = ui.ask_agents(write, read, hosts, list(choice.agents or []), color)
    choice = replace(choice, agents=selected)
    layout, skill_files = preview(choice, root, home)
    if choice.model_review and not choice.no_skills and selected:
        loaded, tiers = models.initial_maps(layout.db, home, root, selected)
        loaded, tiers = models.apply_overrides(
            loaded,
            tiers,
            choice.role_tiers,
            choice.tier_models,
            choice.role_models,
        )
        catalogs = host_models.discover_all(selected, home, root)
        loaded, tiers = ui.ask_models(write, read, selected, loaded, tiers, catalogs, color)
        choice = replace(
            choice,
            model_review=False,
            role_tiers=None,
            tier_models=None,
            role_models=None,
            profiles_map=loaded,
            tiers_map=tiers,
        )
    labels = {host.key: host.label for host in hosts}
    plugins = (
        []
        if hooks_mode == "off"
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


def setup_skipped(cmd: str | None, args: Any) -> bool:
    if os.environ.get(NO_SETUP_ENV, "").strip():
        return True
    return cmd in SKIP_COMMANDS or bool(getattr(args, "version", False))


def explicit_db(args: Any) -> str | None:
    return str(getattr(args, "db", "") or os.environ.get("LAZYPLAN_DB", "") or "") or None


def prompt_allowed(args: Any, interactive: bool | None) -> bool:
    if getattr(args, "json", False) or getattr(args, "yes", False):
        return False
    return ui.stdin_tty() and sys.stderr.isatty() if interactive is None else interactive
