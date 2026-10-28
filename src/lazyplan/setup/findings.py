"""Setup findings."""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import skills, templates, textfile
from ..repo import (
    CONFIG_NAME,
    PLAN_DIR,
    TEMPLATES_DIR_NAME,
    find_repo_root,
    legacy_db_candidates,
    legacy_plan_dir,
    repo_plan_db_path,
    shared_db_path,
    stale_plan_dirs,
    walk_up_team_db,
)
from . import layout, ui
from .constants import (
    HOME,
    REPO,
)
from .layout import SetupChoice
from .moves import move_repo_db
from .state import SetupState, git_state, load_state, plans_in, save_state


@dataclass
class Finding:
    """One layout observation that setup may act on."""

    key: str
    kind: str
    path: Path
    detail: str
    state: str = ""

    @property
    def fingerprint(self) -> str:
        return f"{self.kind}:{self.path}:{self.state}"


def default_choice(
    cwd: Path, home: Path | None = None, state: SetupState | None = None
) -> SetupChoice:
    """Silent defaults: keep an existing repo DB, otherwise use the home DB."""
    state = state or SetupState()
    repo = find_repo_root(cwd)
    team_db = walk_up_team_db(cwd)
    placement = REPO if team_db is not None else state.placement
    agents = state.agents or None
    return SetupChoice(
        placement=placement if repo is not None or placement == REPO else HOME,
        agents=agents,
        skills_dir=state.skills_dir or None,
    )


def parse_agents(raw: str, home: Path) -> list[str]:
    from ..skills import detect_agents, parse_tool_selection

    hosts = detect_agents(home)
    text = (raw or "").strip()
    if not text:
        return [host.key for host in hosts if host.detected]
    if text.lower() == "none":
        return []
    return parse_tool_selection(text, hosts)


def choice_from_args(
    args: Any,
    cwd: Path,
    home: Path | None = None,
    state: SetupState | None = None,
) -> SetupChoice:
    """Build the choice setup would write from flags, state, and the repo."""
    home = home or Path.home()
    state = state or load_state(home)
    explicit = str(getattr(args, "db", "") or os.environ.get("LAZYPLAN_DB", "") or "") or None
    placement = str(getattr(args, "placement", "") or "").strip()
    if placement not in (HOME, REPO):
        placement = (
            state.placement
            if state.last_version
            else (REPO if walk_up_team_db(cwd) is not None else HOME)
        )
    if find_repo_root(cwd) is None:
        placement = HOME
    raw_agents = str(getattr(args, "agents", "") or os.environ.get("LAZYPLAN_AGENTS", "")).strip()
    if raw_agents:
        agents = parse_agents(raw_agents, home)
    else:
        agents = state.agents or parse_agents("", home)
    skills_dir = (
        str(getattr(args, "skills_dir", "") or "").strip()
        or os.environ.get("LAZYPLAN_SKILLS_DIR", "").strip()
        or state.skills_dir
        or None
    )
    return SetupChoice(
        placement=placement,
        agents=agents,
        skills_dir=skills_dir,
        no_skills=bool(getattr(args, "no_skills", False)),
        explicit_db=explicit,
    )


def preview(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
) -> tuple[layout.SetupLayout, list[Path]]:
    """Resolve the paths the choice would write, without writing."""
    skill_plan = skills.plan_choice(choice, root, home)
    resolved = layout.resolve_choice(choice, root, skill_plan, home)
    return resolved, list(skill_plan.skill_files)


def _installed_skill_files(home: Path) -> list[Path]:
    targets = [home / skills.AGENTS_DIR / skills.SKILLS_DIR / skills.SKILL_NAME / "SKILL.md"]
    for tool in skills.KNOWN_TOOLS:
        entry = skills.TOOL_SKILL_DIRS.get(tool)
        if entry is None or not entry[1]:
            continue
        targets.append(home / entry[1] / skills.SKILL_NAME / "SKILL.md")
    seen: list[Path] = []
    for path in targets:
        if path not in seen:
            seen.append(path)
    return seen


def refresh_installed_skills(home: Path | None = None) -> tuple[list[Path], list[Path]]:
    """Refresh old generated skill copies, backing up every changed file."""
    home = home or Path.home()
    refreshed: list[Path] = []
    backups: list[Path] = []
    backup_root: Path | None = None
    marker = "name: lazyplan"
    for path in _installed_skill_files(home):
        try:
            if not path.is_file():
                continue
            text = textfile.read(path)
        except OSError:
            continue
        if text == skills.render_skill() or marker not in text[:500]:
            continue
        if backup_root is None:
            backup_root = layout.new_backup_dir(home)
        backups.append(layout.backup_file(backup_root, path))
        changed, _status = skills.write_skill_file(path)
        if changed:
            refreshed.append(path)
    return refreshed, backups


def cleanup_repo_artifacts(root: Path, home: Path) -> list[str]:
    """Remove generated repo resources after a switch to home placement."""
    plan_dir = root / PLAN_DIR
    templates_dir = plan_dir / TEMPLATES_DIR_NAME
    skill_files = [entry / "SKILL.md" for entry in layout._repo_skill_dirs(root)]
    touched = [
        plan_dir / CONFIG_NAME,
        *skill_files,
        root / "AGENTS.md",
        root / ".gitignore",
    ]
    touched.extend(templates_dir / name for name in templates.TEMPLATE_FILES.values())
    backups = layout.new_backup_dir(home)
    for path in touched:
        if path.is_file():
            layout.backup_file(backups, path)
    if (root / "AGENTS.md").is_file():
        layout._strip_agents(root / "AGENTS.md")
    if (root / ".gitignore").is_file():
        layout._strip_gitignore(root / ".gitignore")
    for path in (root / "AGENTS.md", root / ".gitignore"):
        if path.is_file() and not textfile.read(path).strip():
            path.unlink()
    for path in skill_files:
        if path.is_file():
            path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
    if (plan_dir / CONFIG_NAME).is_file():
        (plan_dir / CONFIG_NAME).unlink()
    for kind, name in templates.TEMPLATE_FILES.items():
        path = templates_dir / name
        if path.is_file() and textfile.read(path) == templates.STARTERS.get(kind):
            path.unlink()
    try:
        templates_dir.rmdir()
        plan_dir.rmdir()
    except OSError:
        pass
    return [str(backups)] if backups.exists() else []


def review_findings(
    findings: list[Finding],
    state: SetupState,
    home: Path | None = None,
    root: Path | None = None,
    read: Any = None,
    write: Any = None,
    color: bool = False,
    allow_prompt: bool = True,
    json_mode: bool = False,
) -> list[str]:
    """Offer one choice per undecided finding; remember the answer."""
    home = home or Path.home()
    write = write or sys.stderr
    read = read or (lambda: input(""))
    notes: list[str] = []
    for finding in findings:
        if finding.fingerprint in state.decisions:
            continue
        if finding.kind != "repo-db":
            if finding.kind == "db-conflict":
                notes.append(
                    "both databases contain plans; export one with "
                    "`lpui export --format json` and import it before moving"
                )
            elif finding.kind in ("legacy-dir", "stale-dir"):
                notes.append(f"{finding.detail} at {finding.path} is not used by this version")
            elif finding.kind == "legacy-db":
                notes.append(
                    f"older database at {finding.path} is no longer read; "
                    "import it with `lpui import --file` or delete it"
                )
            elif finding.kind == "repo-resources":
                notes.append(
                    f"repo resources at {finding.path} are ignored while plans live at home; "
                    "run `lpui setup --placement repo` to use them"
                )
            elif finding.kind == "stale-skill":
                notes.append(f"older skill copy at {finding.path} is refreshed with a backup")
            continue
        if finding.state == "tracked":
            notes.append(f"{finding.path} is tracked by git; leaving it in place")
            continue
        if not allow_prompt:
            notes.append(
                f"repo database {finding.path} is {finding.state}; run `lpui setup` to move it home"
            )
            continue
        action = ui.ask_migration(
            write,
            read,
            finding.path,
            finding.state,
            shared_db_path(home),
            color,
        )
        if action == "move":
            ok, message = move_repo_db(finding.path, home, root)
            notes.append(message)
            if not ok:
                # A refused move must stay armed for the next human run.
                continue
            state.placement = HOME
        from .apply import record_finding

        record_finding(state, finding, action)
        save_state(state, home)
    return notes


def detect_findings(
    cwd: Path,
    home: Path | None = None,
    state: SetupState | None = None,
    explicit_db: str | None = None,
) -> list[Finding]:
    """Layout drift worth a note or a one-time choice (read-only)."""
    if explicit_db:
        return []
    home = home or Path.home()
    state = state or SetupState()
    root = find_repo_root(cwd)
    out: list[Finding] = []
    if root is not None:
        repo_db = repo_plan_db_path(root)
        if repo_db.is_file() and state.placement != REPO:
            gstate = git_state(root)
            out.append(
                Finding(
                    key=f"repo-db:{repo_db}",
                    kind="repo-db",
                    path=repo_db,
                    detail="repo database",
                    state=gstate,
                )
            )
        if repo_db.is_file():
            home_db = shared_db_path(home)
            if home_db.is_file() and plans_in(repo_db) > 0 and plans_in(home_db) > 0:
                out.append(
                    Finding(
                        key=f"db-conflict:{repo_db}",
                        kind="db-conflict",
                        path=repo_db,
                        detail="both databases contain plans",
                        state="conflict",
                    )
                )
        legacy = legacy_plan_dir(root)
        if legacy.is_dir():
            out.append(
                Finding(
                    key=f"legacy:{legacy}",
                    kind="legacy-dir",
                    path=legacy,
                    detail="legacy .plan directory",
                )
            )
        for stale in stale_plan_dirs(root):
            out.append(
                Finding(
                    key=f"stale:{stale}",
                    kind="stale-dir",
                    path=stale,
                    detail="pre-move plan directory",
                )
            )
        out.extend(_repo_resource_findings(root, state))
    out.extend(legacy_db_findings(home))
    out.extend(_stale_skill_findings(home))
    return out


def _repo_resource_findings(root: Path, state: SetupState) -> list[Finding]:
    """Repo templates/config/skills ignored while plans live at home."""
    if state.placement != HOME:
        return []
    plan_dir = root / PLAN_DIR
    shared = repo_plan_db_path(root)
    if shared.is_file() or not plan_dir.is_dir():
        return []
    return [
        Finding(
            key=f"repo-resources:{plan_dir}",
            kind="repo-resources",
            path=plan_dir,
            detail="repo resources while plans live at home",
        )
    ]


def legacy_db_findings(home: Path) -> list[Finding]:
    """Old per-agent databases that resolution no longer reads."""
    home_db = shared_db_path(home)
    out: list[Finding] = []
    for path in legacy_db_candidates(home):
        if path == home_db or not path.is_file():
            continue
        out.append(
            Finding(
                key=f"legacy-db:{path}",
                kind="legacy-db",
                path=path,
                detail="old per-agent database",
            )
        )
    return out


def _stale_skill_findings(home: Path) -> list[Finding]:
    """Installed generated skill copies older than the current render."""
    current = skills.render_skill()
    out: list[Finding] = []
    for path in _installed_skill_files(home):
        try:
            if not path.is_file():
                continue
            text = textfile.read(path)
        except OSError:
            continue
        if text == current or "name: lazyplan" not in text[:500]:
            continue
        out.append(
            Finding(
                key=f"stale-skill:{path}",
                kind="stale-skill",
                path=path,
                detail="outdated generated skill",
                state=hashlib.sha256(text.encode()).hexdigest()[:12],
            )
        )
    return out
