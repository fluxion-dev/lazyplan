"""Setup apply."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .. import hook_install, skills, textfile
from ..repo import (
    find_repo_root,
)
from ..store import Store
from . import layout, ui
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
from .layout import SetupChoice
from .state import SetupState, _timestamp, load_state, save_state, state_path
from .wizard import _explicit_db, _prompt_allowed, _setup_skipped, run_wizard


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
    if (
        not choice.explicit_db
        and root is not None
        and previous.placement == REPO
        and choice.placement != REPO
    ):
        cleanup_repo_artifacts(root, home)
    skill_plan = skills.plan_choice(choice, root, home)
    resolved = layout.resolve_choice(choice, root, skill_plan, home)
    layout.apply_layout(resolved, interactive=False, read=None, write=out)
    store = Store(str(resolved.db))
    # Back up old generated copies before the installer rewrites the same paths.
    refreshed, backups = refresh_installed_skills(home)
    result = skills.apply_skill_plan(skill_plan, root, home)
    if root is not None and choice.placement == REPO and not choice.explicit_db:
        for entry in resolved.gitignore_entries:
            skills.append_gitignore(root, entry)
    state = load_state(home)
    state.version = SETUP_VERSION
    state.placement = REPO if resolved.storage == layout.STORAGE_REPO else HOME
    state.agents = list(choice.agents or [])
    state.skills_dir = choice.skills_dir or ""
    state.explicit_db = bool(choice.explicit_db)
    state.last_version = version or state.last_version
    save_state(state, home)
    return {
        "db": str(store.path),
        "templates": str(resolved.templates_dir),
        "config": str(resolved.config) if resolved.config else None,
        "skills": [str(path) for path in skill_plan.skill_files],
        "installed": result.installed,
        "refreshed": [str(path) for path in refreshed],
        "backups": [str(path) for path in backups],
        "state": str(state_path(home)),
        "placement": state.placement,
        "agents": list(choice.agents or []),
        "explicit": bool(choice.explicit_db),
    }


def install_hooks(
    home: Path,
    agents: list[str] | None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Install or remove managed hooks and remember the decision."""
    if enabled is False:
        report = hook_install.remove(home)
    else:
        hosts = None if agents is None else [host for host in agents if host in hook_install.HOSTS]
        report = hook_install.install(home, hosts=hosts)
    state = load_state(home)
    planned = None if agents is None else [h for h in agents if h in hook_install.HOSTS]
    state.hook_files = (
        []
        if enabled is False
        else [str(spec.path) for spec in hook_install.preview(home, planned) if spec.path.is_file()]
    )
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
    hook_mode: bool | None = None,
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


def _record(state: SetupState, finding: Finding, decision: str) -> None:
    state.decisions[finding.fingerprint] = {
        "decision": decision,
        "seen_at": _timestamp(),
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
    """First-run setup and upgrade review; never blocks agent commands."""
    if _setup_skipped(cmd, args):
        return None
    home = home or Path.home()
    state = load_state(home)
    explicit = _explicit_db(args)
    if explicit:
        # An explicit database is a caller-owned context: never write layout,
        # skills, or state around it.
        return None
    version_changed = state.last_version != (version or "")
    first = not state.last_version
    human = cmd in HUMAN_COMMANDS
    findings = detect_findings(cwd, home, state, None) if human else []
    if not first and not version_changed and not findings:
        return None
    can_prompt = _prompt_allowed(args, interactive)
    root = find_repo_root(cwd)
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
            hooks_enabled=getattr(args, "hooks", None),
        )
        if result is None:
            return None
    else:
        result = apply_choice(choice, root, home, version)
    install_integrations(
        result,
        home,
        root,
        getattr(args, "hooks", None),
        getattr(args, "agents_pointer", None),
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
