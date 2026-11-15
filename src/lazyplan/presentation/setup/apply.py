"""Setup apply."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from lazyplan.core.policies import hooks as hook_policy
from lazyplan.infrastructure import agent_install, hook_install, profiles, skills, textfile
from lazyplan.infrastructure.integrations import HOOK
from lazyplan.infrastructure.repo import (
    find_repo_root,
)

from ...store import Store
from . import layout, models, ui
from .constants import (
    HOME,
    HUMAN_COMMANDS,
    REPO,
    SETUP_VERSION,
)
from .findings import (
    Finding,
    choice_from_args,
    cleanup_repo_artifacts,
    detect_findings,
    refresh_installed_skills,
    review_findings,
)
from .integrations import Inspection, inspect, remember_installed, review_pending
from .layout import SetupChoice
from .state import SetupState, load_state, save_state, state_path, timestamp
from .wizard import explicit_db, prompt_allowed, run_wizard, setup_skipped


def _seed_profile_map(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    db_path: Path,
    agents: list[str],
) -> tuple[Path | None, Path | None]:
    """Write or migrate agents.json; return its path and backup, if any."""
    if choice.explicit_db or not agents:
        return None, None
    path = profiles.path_for(db_path)
    loaded, effective = models.initial_maps(db_path, home, root, agents)
    if choice.profiles_map is not None:
        loaded = dict(choice.profiles_map)
    if choice.tiers_map is not None:
        effective = {tier: dict(values) for tier, values in choice.tiers_map.items()}
    updated, effective = models.apply_overrides(
        loaded,
        effective,
        choice.role_tiers,
        choice.tier_models,
        choice.role_models,
    )
    text = profiles.render(updated, effective)
    if path.is_file() and textfile.read(path) == text:
        return path, None
    backup: Path | None = None
    if path.is_file():
        backup_dir = layout.new_backup_dir(home)
        backup = layout.backup_file(backup_dir, path)
    profiles.save(db_path, updated, effective)
    return path, backup


def _remove_deselected_profiles(
    previous: SetupState,
    selected: list[str],
    root: Path | None,
    home: Path,
    scope: str,
) -> list[str]:
    """Remove only marked files for hosts that are no longer selected."""
    dropped = [host for host in previous.agents if host not in set(selected)]
    if not dropped:
        return []
    scopes = {scope}
    if previous.placement == REPO and root is not None:
        scopes.add("project")
    if previous.placement == HOME:
        scopes.add("global")
    removed: list[str] = []
    for host in dropped:
        for current in scopes:
            for path in agent_install.profile_paths(current, root, home, [host]):
                if not path.is_file():
                    continue
                try:
                    text = textfile.read(path)
                except OSError:
                    continue
                if "managed by lazyplan:" not in text:
                    continue
                path.unlink()
                removed.append(str(path))
    return removed


def _install_agent_profiles(
    skill_plan: skills.SkillPlan,
    root: Path | None,
    home: Path,
    db_path: str | Path,
    agents: list[str],
) -> tuple[list[agent_install.AgentInstallResult], list[str]]:
    """Install selected-host profiles and list every target file."""
    results = agent_install.install_profiles(skill_plan.scope, root, home, agents, db_path)
    files = [
        str(path) for path in agent_install.profile_paths(skill_plan.scope, root, home, agents)
    ]
    return results, files


def _maybe_cleanup(
    choice: SetupChoice, root: Path | None, home: Path, previous: SetupState
) -> None:
    """Remove repo resources after a switch back to home placement."""
    if (
        not choice.explicit_db
        and root is not None
        and previous.placement == REPO
        and choice.placement != REPO
    ):
        cleanup_repo_artifacts(root, home)


def _apply_layout(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    out: Any,
    previous: SetupState,
) -> tuple[
    layout.SetupLayout, skills.SkillPlan, Store, skills.InstallResult, list[Path], list[Path]
]:
    """Resolve and write the database, templates, and skill files."""
    skill_plan = skills.plan_choice(choice, root, home)
    resolved = layout.resolve_choice(choice, root, skill_plan, home)
    layout.apply_layout(resolved, interactive=False, read=None, write=out)
    store = Store(str(resolved.db))
    # Back up old generated copies before the installer rewrites the same paths.
    refreshed, backups = refresh_installed_skills(home)
    result = skills.apply_skill_plan(
        skill_plan,
        root,
        home,
        only_existing=bool(previous.last_version and previous.skills_enabled),
    )
    return resolved, skill_plan, store, result, refreshed, backups


def _install_selected(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    resolved: layout.SetupLayout,
    skill_plan: skills.SkillPlan,
    previous: SetupState,
    backups: list[Path],
) -> tuple[list[str], Path | None, list[agent_install.AgentInstallResult], list[str], list[str]]:
    """Seed the map, install profiles, and remove hosts that were dropped."""
    agents = (
        list(choice.agents)
        if choice.agents is not None
        else [host.key for host in skills.detect_agents(home) if host.detected]
    )
    profile_map: Path | None = None
    if skill_plan.scope != "none":
        profile_map, profile_backup = _seed_profile_map(choice, root, home, resolved.db, agents)
        if profile_backup is not None:
            backups.append(profile_backup)
    profile_results, profile_files = _install_agent_profiles(
        skill_plan, root, home, resolved.db, agents
    )
    removed = _remove_deselected_profiles(previous, agents, root, home, skill_plan.scope)
    if root is not None and choice.placement == REPO and not choice.explicit_db:
        for entry in resolved.gitignore_entries:
            skills.append_gitignore(root, entry)
    return agents, profile_map, profile_results, profile_files, removed


def apply_choice(
    choice: SetupChoice,
    root: Path | None,
    home: Path | None = None,
    version: str = "",
    write: Any = None,
) -> dict[str, Any]:
    """Write the database, templates, skills, and remembered state."""
    home = home or Path.home()
    out = write or sys.stderr
    previous = load_state(home)
    _maybe_cleanup(choice, root, home, previous)
    resolved, skill_plan, store, result, refreshed, backups = _apply_layout(
        choice, root, home, out, previous
    )
    agents, profile_map, profile_results, profile_files, removed_profiles = _install_selected(
        choice, root, home, resolved, skill_plan, previous, backups
    )
    state = _remember_choice(home, choice, resolved, skill_plan, version, profile_files)
    return {
        "db": str(store.path),
        "templates": str(resolved.templates_dir),
        "config": str(resolved.config) if resolved.config else None,
        "skills": [str(path) for path in skill_plan.skill_files],
        "installed": result.installed,
        "agents_json": str(profile_map) if profile_map is not None else None,
        "profiles": [item.to_dict() for item in profile_results],
        "profile_files": profile_files,
        "removed_profiles": removed_profiles,
        "refreshed": [str(path) for path in refreshed],
        "backups": [str(path) for path in backups],
        "state": str(state_path(home)),
        "placement": state.placement,
        "agents": agents,
        "explicit": bool(choice.explicit_db),
    }


def _remember_choice(
    home: Path,
    choice: SetupChoice,
    resolved: layout.SetupLayout,
    skill_plan: skills.SkillPlan,
    version: str,
    profile_files: list[str] | None = None,
) -> SetupState:
    """Persist the resolved placement, agents, and last setup version."""
    state = load_state(home)
    state.version = SETUP_VERSION
    state.placement = REPO if resolved.storage == layout.STORAGE_REPO else HOME
    state.agents = list(choice.agents or [])
    state.skills_dir = choice.skills_dir or ""
    if not choice.explicit_db:
        state.skills_enabled = skill_plan.scope != "none"
    if profile_files is not None:
        state.profile_files = list(profile_files)
    state.explicit_db = bool(choice.explicit_db)
    state.last_version = version or state.last_version
    save_state(state, home)
    return state


def install_hooks(
    home: Path,
    agents: list[str] | None,
    mode: str | bool | None = None,
) -> dict[str, Any]:
    """Install or remove managed hooks in one mode and remember the decision."""
    state = load_state(home)
    flag: str | bool | None = mode
    stored = (
        (
            state.hooks_mode
            if flag is True and state.hooks_mode in ("strict", "advisory")
            else "strict"
        )
        if flag is True
        else state.effective_mode()
    )
    resolved = hook_policy.resolve_mode(flag, stored, os.environ)
    planned = None if agents is None else [h for h in agents if h in hook_install.HOSTS]
    if resolved == "off":
        report = hook_install.remove(home)
    else:
        report = hook_install.install(home, hosts=planned, mode=resolved)
    state.hook_files = (
        []
        if resolved == "off"
        else [str(spec.path) for spec in hook_install.preview(home, planned) if spec.path.is_file()]
    )
    state.hooks_enabled = resolved != "off"
    state.hooks_mode = resolved
    state.hooks = bool(state.hook_files)
    save_state(state, home)
    return report


def install_pointer(
    home: Path,
    placement: str,
    root: Path | None,
    db_path: Path,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Add or remove the opt-in AGENTS.md section for home placement."""
    state = load_state(home)
    want = enabled if enabled is not None else state.agents_pointer
    if placement != HOME or root is None or (not want and enabled is None):
        state.agents_pointer = False
        state.agents_file = ""
        save_state(state, home)
        return {"enabled": False, "path": None, "status": "skipped"}
    path = root / "AGENTS.md"
    if not want:
        changed, status = skills.remove_agents_md(root)
        state.agents_pointer = False
        state.agents_file = ""
        save_state(state, home)
        return {"enabled": False, "path": str(path) if changed else None, "status": status}
    snippet = skills.render_home_agents_snippet(db_path)
    if path.is_file():
        try:
            text = textfile.read(path)
        except OSError:
            text = ""
        if not (skills.AGENTS_MARK_BEGIN in text and snippet.strip() in text):
            backup = layout.new_backup_dir(home)
            layout.backup_file(backup, path)
    changed, status = skills.ensure_agents_md(root, snippet)
    state.agents_pointer = True
    state.agents_file = str(path)
    save_state(state, home)
    return {"enabled": True, "path": str(path) if changed else None, "status": status}


def install_integrations(
    result: dict[str, Any],
    home: Path,
    root: Path | None,
    hook_mode: str | bool | None = None,
    pointer_mode: bool | None = None,
) -> dict[str, Any]:
    """Install hooks and the optional pointer for a completed layout."""
    result["hooks"] = install_hooks(home, result.get("agents"), hook_mode)
    result["agents_pointer"] = install_pointer(
        home,
        str(result.get("placement", "")),
        root,
        Path(result["db"]),
        pointer_mode,
    )
    return result


def refresh_installed_hooks(
    inspection: Inspection,
    state: SetupState,
    home: Path,
) -> dict[str, Any]:
    """Refresh fully installed hook hosts without adding catalog items."""
    if not state.hooks_enabled:
        return {"installed": [], "backups": [], "skipped": []}
    installed = {item.host for item in inspection.installed if item.kind == HOOK}
    pending = {item.host for item in inspection.pending if item.kind == HOOK}
    hosts = sorted(installed - pending)
    if not hosts:
        return {"installed": [], "backups": [], "skipped": []}
    return hook_install.install(home, hosts=hosts, mode=state.hooks_mode)


def refresh_integrations(
    result: dict[str, Any],
    choice: SetupChoice,
    home: Path,
    root: Path | None,
    version: str,
    read: Any = None,
    write: Any = None,
    color: bool = False,
    allow_prompt: bool = True,
    pointer_mode: bool | None = None,
) -> dict[str, Any]:
    """Refresh installed items, then offer only the pending additions."""
    state = load_state(home)
    inspection = inspect(choice, state, root, home, version)
    if remember_installed(inspection, state, version):
        save_state(state, home)
    result["hooks"] = refresh_installed_hooks(inspection, state, home)
    if state.profile_files and state.agents and not state.explicit_db:
        db_path = Path(result["db"])
        scope = "project" if state.placement == REPO and root is not None else "global"
        _seed_profile_map(choice_from_state(state), root, home, db_path, state.agents)
        result["profiles"] = [
            item.to_dict()
            for item in agent_install.install_profiles(scope, root, home, state.agents, db_path)
        ]
    result["agents_pointer"] = install_pointer(
        home,
        str(result.get("placement", "")),
        root,
        Path(result["db"]),
        pointer_mode,
    )
    review = review_pending(
        choice,
        state,
        root,
        home,
        version,
        read=read or (lambda: ""),
        write=write or sys.stderr,
        color=color,
        allow_prompt=allow_prompt,
    )
    result["integration_review"] = review.to_dict()
    return result


def choice_from_state(state: SetupState) -> SetupChoice:
    """Rebuild the effective setup choice from remembered state."""
    return SetupChoice(
        placement=state.placement,
        agents=list(state.agents) or None,
        skills_dir=state.skills_dir or None,
        no_skills=not state.skills_enabled,
        explicit_db=None,
    )


def record_finding(state: SetupState, finding: Finding, decision: str) -> None:
    state.decisions[finding.fingerprint] = {
        "decision": decision,
        "seen_at": timestamp(),
        "path": str(finding.path),
        "state": finding.state,
    }


def ensure(
    cmd: str | None,
    args: Any,
    cwd: Path,
    home: Path | None = None,
    version: str = "",
    interactive: bool | None = None,
) -> dict[str, Any] | None:
    """First-run setup and upgrade refresh; never blocks agent commands.

    Pending integrations are left for the TUI's health check to offer.
    """
    if setup_skipped(cmd, args):
        return None
    home = home or Path.home()
    state = load_state(home)
    explicit = explicit_db(args)
    if explicit:
        # An explicit database is a caller-owned context: never write layout,
        # skills, or state around it.
        return None
    version_changed = state.last_version != (version or "")
    first = not state.last_version
    human = cmd in HUMAN_COMMANDS
    findings = detect_findings(cwd, home, state, None) if human else []
    can_prompt = prompt_allowed(args, interactive)
    root = find_repo_root(cwd)
    if not first and not version_changed and not findings:
        return None
    result: dict[str, Any] | None = None
    if first or version_changed:
        result = _run_setup_once(args, cwd, home, state, version, root, human, can_prompt, first)
        if result is None:
            return None
    if human and findings:
        _review_setup(args, findings, home, root, can_prompt)
    return result


def _run_setup_once(
    args: Any,
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    root: Path | None,
    human: bool,
    can_prompt: bool,
    first: bool,
) -> dict[str, Any] | None:
    choice = choice_from_args(args, cwd, home, state)
    if human and can_prompt and first:
        result = run_wizard(
            cwd,
            home,
            state,
            version,
            json_mode=bool(getattr(args, "json", False)),
            initial=choice,
            hooks_mode=getattr(args, "hooks", None),
        )
        if result is None:
            return None
    else:
        result = apply_choice(choice, root, home, version)
    if first:
        install_integrations(
            result,
            home,
            root,
            getattr(args, "hooks", None),
            getattr(args, "agents_pointer", None),
        )
        current = load_state(home)
        adopted_choice = choice_from_state(current)
        inspection = inspect(adopted_choice, current, root, home, version)
        if remember_installed(inspection, current, version):
            save_state(current, home)
    else:
        refresh_integrations(
            result,
            choice,
            home,
            root,
            version,
            allow_prompt=False,
            pointer_mode=getattr(args, "agents_pointer", None),
        )
    if first and human and not getattr(args, "json", False):
        _announce_setup(result)
    return result


def _announce_setup(result: dict[str, Any]) -> None:
    hooks = result.get("hooks") or {}
    ui.success(
        sys.stderr,
        Path(result["db"]),
        [Path(path) for path in result["skills"]],
        [Path(path) for path in hooks.get("backups") or []],
        ui.color_enabled(sys.stderr, False),
        [Path(path) for path in hooks.get("installed") or []],
    )


def _review_setup(
    args: Any,
    findings: list[Finding],
    home: Path,
    root: Path | None,
    can_prompt: bool,
) -> None:
    review_findings(
        findings,
        load_state(home),
        home,
        root,
        write=sys.stderr,
        color=ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
        allow_prompt=can_prompt,
        json_mode=bool(getattr(args, "json", False)),
    )
