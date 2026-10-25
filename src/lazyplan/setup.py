"""First-run setup: remembered choices, placement, findings, and safe moves.

Setup runs before the database opens, remembers what it installed in `~/.lazyplan/setup.json`, and reviews layout drift once per finding
instead of nagging on every upgrade. Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import setup_layout, setup_ui, skills
from .repo import (
    find_repo_root,
    legacy_plan_dir,
    repo_plan_db_path,
    shared_db_path,
    shared_home,
    stale_plan_dirs,
    walk_up_team_db,
)
from .setup_layout import SetupChoice
from .store import Store

SETUP_VERSION = 1
STATE_NAME = "setup.json"
HOME = "home"
REPO = "repo"


def state_path(home: Path | None = None) -> Path:
    """Shared setup state file; never inside a repo plan dir."""
    return shared_home(home) / STATE_NAME


@dataclass
class SetupState:
    version: int = SETUP_VERSION
    placement: str = HOME
    agents: list[str] = field(default_factory=list)
    skills_dir: str = ""
    explicit_db: bool = False
    last_version: str = ""
    hooks: bool = False
    hook_files: list[str] = field(default_factory=list)
    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "placement": self.placement,
            "agents": list(self.agents),
            "skills_dir": self.skills_dir,
            "explicit_db": self.explicit_db,
            "last_version": self.last_version,
            "hooks": self.hooks,
            "hook_files": list(self.hook_files),
            "decisions": self.decisions,
        }

    @classmethod
    def from_dict(cls, raw: object) -> SetupState:
        """Tolerant parse: unknown shapes fall back to defaults."""
        if not isinstance(raw, dict):
            return cls()
        placement = raw.get("placement")
        agents = raw.get("agents")
        decisions = raw.get("decisions")
        return cls(
            version=int(raw.get("version", SETUP_VERSION) or SETUP_VERSION),
            placement=placement if placement in (HOME, REPO) else HOME,
            agents=[str(a) for a in agents] if isinstance(agents, list) else [],
            skills_dir=str(raw.get("skills_dir", "") or ""),
            explicit_db=bool(raw.get("explicit_db", False)),
            last_version=str(raw.get("last_version", "") or ""),
            hooks=bool(raw.get("hooks", False)),
            hook_files=[str(p) for p in raw.get("hook_files", [])]
            if isinstance(raw.get("hook_files"), list)
            else [],
            decisions=decisions if isinstance(decisions, dict) else {},
        )


def load_state(home: Path | None = None) -> SetupState:
    """Read setup state; missing or corrupt files return defaults."""
    path = state_path(home)
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return SetupState()
    return SetupState.from_dict(raw)


def save_state(state: SetupState, home: Path | None = None) -> Path:
    """Write setup state atomically and return the path."""
    path = state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
    os.replace(tmp, path)
    return path


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


def plans_in(path: str | Path) -> int:
    """Read-only plan count for a database; -1 when unreadable."""
    try:
        conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM plans").fetchone()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        return -1
    return int(row[0]) if row else 0


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")


def backup_dir(home: Path | None = None) -> Path:
    """Fresh backup directory under the shared home."""
    path = shared_home(home) / "backups" / _timestamp()
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_file(source: str | Path, home: Path | None = None) -> Path | None:
    """Copy one file into a fresh backup dir, preserving its relative path."""
    src = Path(source)
    try:
        if not src.is_file():
            return None
    except OSError:
        return None
    dest = backup_dir(home) / src.name
    try:
        shutil.copy2(src, dest)
    except OSError:
        return None
    return dest


def git_state(repo_root: Path) -> str:
    """Tracked, ignored, or untracked for the repo plan database."""
    db = repo_plan_db_path(repo_root)
    rel = db.relative_to(repo_root).as_posix()
    try:
        tracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return "untracked"
    if tracked.returncode == 0:
        return "tracked"
    try:
        ignored = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return "untracked"
    return "ignored" if ignored.returncode == 0 else "untracked"


@dataclass(frozen=True)
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


HUMAN_COMMANDS = ("ui", "setup", "upgrade")
SKIP_COMMANDS = ("setup", "upgrade", "completion", "doctor", "audit", "brief", "hook", "help")
NO_SETUP_ENV = "LAZYPLAN_NO_SETUP"


def _parse_agents(raw: str, home: Path) -> list[str]:
    from .skills import detect_agents, parse_tool_selection

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
        agents = _parse_agents(raw_agents, home)
    else:
        agents = state.agents or _parse_agents("", home)
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
) -> tuple[setup_layout.SetupLayout, list[Path]]:
    """Resolve the paths the choice would write, without writing."""
    skill_plan = skills.plan_choice(choice, root, home)
    layout = setup_layout.resolve_choice(choice, root, skill_plan, home)
    return layout, list(skill_plan.skill_files)


def _installed_skill_files(home: Path) -> list[Path]:
    targets = [home / ".agents" / "skills" / skills.SKILL_NAME / "SKILL.md"]
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
    marker = "name: lazyplan"
    for path in _installed_skill_files(home):
        try:
            if not path.is_file():
                continue
            text = path.read_text()
        except OSError:
            continue
        if text == skills.render_skill() or marker not in text[:500]:
            continue
        backup = backup_file(path, home)
        if backup is not None:
            backups.append(backup)
        changed, _status = skills.write_skill_file(path)
        if changed:
            refreshed.append(path)
    return refreshed, backups


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
    skill_plan = skills.plan_choice(choice, root, home)
    layout = setup_layout.resolve_choice(choice, root, skill_plan, home)
    setup_layout.apply_layout(layout, interactive=False, read=None, write=out)
    store = Store(str(layout.db))
    # Back up old generated copies before the installer rewrites the same paths.
    refreshed, backups = refresh_installed_skills(home)
    result = skills.apply_skill_plan(skill_plan, root, home)
    if root is not None and choice.placement == REPO and not choice.explicit_db:
        for entry in layout.gitignore_entries:
            skills.append_gitignore(root, entry)
    state = load_state(home)
    state.version = SETUP_VERSION
    state.placement = REPO if layout.storage == setup_layout.STORAGE_REPO else HOME
    state.agents = list(choice.agents or [])
    state.skills_dir = choice.skills_dir or ""
    state.explicit_db = bool(choice.explicit_db)
    state.last_version = version or state.last_version
    save_state(state, home)
    return {
        "db": str(store.path),
        "templates": str(layout.templates_dir),
        "config": str(layout.config) if layout.config else None,
        "skills": [str(path) for path in skill_plan.skill_files],
        "installed": result.installed,
        "refreshed": [str(path) for path in refreshed],
        "backups": [str(path) for path in backups],
        "state": str(state_path(home)),
        "placement": state.placement,
        "explicit": bool(choice.explicit_db),
    }


def run_wizard(
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    read: Any = None,
    write: Any = None,
    json_mode: bool = False,
) -> dict[str, Any] | None:
    """Ask placement and agents, review, then apply. None means cancelled."""
    read = read or (lambda: input(""))
    write = write or sys.stderr
    color = setup_ui.color_enabled(write, json_mode)
    try:
        return _run_wizard(cwd, home, state, version, read, write, color)
    except (EOFError, KeyboardInterrupt):
        setup_ui.note(write, "Setup cancelled; nothing was written.", color, "warn")
        return None


def _run_wizard(
    cwd: Path,
    home: Path,
    state: SetupState,
    version: str,
    read: Any,
    write: Any,
    color: bool,
) -> dict[str, Any] | None:
    root = find_repo_root(cwd)
    setup_ui.banner(write, color, version)
    repo_db = repo_plan_db_path(root) if root is not None else None
    default_placement = REPO if repo_db is not None and repo_db.is_file() else state.placement
    if default_placement not in (HOME, REPO):
        default_placement = HOME
    placement = setup_ui.ask_placement(write, read, root, home, default_placement, color)
    choice = SetupChoice(
        placement=placement,
        agents=state.agents or _parse_agents("", home),
        skills_dir=state.skills_dir or None,
    )
    hosts = skills.detect_agents(home)
    selected = setup_ui.ask_agents(write, read, hosts, list(choice.agents or []), color)
    choice = SetupChoice(
        placement=placement,
        agents=selected,
        skills_dir=choice.skills_dir,
    )
    layout, skill_files = preview(choice, root, home)
    setup_ui.render_review(
        write,
        layout.db,
        layout.templates_dir,
        skill_files,
        state_path(home),
        layout.config,
        color,
    )
    if not setup_ui.confirm(write, read, color):
        setup_ui.note(write, "Setup cancelled; nothing was written.", color, "warn")
        return None
    result = apply_choice(choice, root, home, version, write)
    setup_ui.success(write, Path(result["db"]), [Path(p) for p in result["skills"]], [], color)
    return result


def _record(state: SetupState, finding: Finding, decision: str) -> None:
    state.decisions[finding.fingerprint] = {
        "decision": decision,
        "seen_at": _timestamp(),
        "path": str(finding.path),
        "state": finding.state,
    }


def _move_sources(repo_db: Path, root: Path | None) -> list[Path]:
    """Every file a move touches, in backup order."""
    sources = [repo_db]
    config = repo_db.parent / "config.json"
    templates = repo_db.parent / "templates"
    if config.is_file():
        sources.append(config)
    if templates.is_dir():
        sources.append(templates)
    if root is not None:
        for name in ("AGENTS.md", ".gitignore"):
            path = root / name
            if path.is_file():
                sources.append(path)
    return sources


def _merge_templates(source: Path, dest: Path) -> None:
    """Move loose template files home without overwriting existing ones."""
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = dest / item.name
        if item.is_file() and not target.exists():
            shutil.move(str(item), str(target))


def _strip_repo_markers(root: Path) -> None:
    """Remove the generated AGENTS.md block and gitignore lines after a move."""
    agents = root / "AGENTS.md"
    if agents.is_file():
        setup_layout._strip_agents(agents)
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        setup_layout._strip_gitignore(gitignore)


def _prune_moved_dirs(repo_dir: Path, templates: Path) -> None:
    """Remove only the empty directories a move emptied."""
    try:
        if templates.is_dir() and not any(templates.iterdir()):
            templates.rmdir()
        if repo_dir.is_dir() and not any(repo_dir.iterdir()):
            repo_dir.rmdir()
    except OSError:
        pass


def move_repo_db(
    repo_db: Path,
    home: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Move an untracked repo database home after backing up every touched file."""
    home = home or Path.home()
    home_db = shared_db_path(home)
    repo_db = Path(repo_db)
    if home_db.is_file() and plans_in(home_db) > 0 and plans_in(repo_db) > 0:
        return (
            False,
            "both databases contain plans; export one and import it before moving",
        )
    root = repo_root or (
        repo_db.parent.parent.parent if repo_db.parent.name == "lazyplan" else None
    )
    backups = setup_layout._new_backup_dir(home)
    for source in _move_sources(repo_db, root):
        setup_layout._backup_file(backups, source)
    if home_db.is_file():
        setup_layout._backup_file(backups, home_db)
        home_db.unlink()
    home_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(repo_db), str(home_db))
    templates = repo_db.parent / "templates"
    config = repo_db.parent / "config.json"
    if templates.is_dir():
        _merge_templates(templates, home_db.parent / "templates")
    if config.is_file():
        config.unlink()
    if root is not None:
        _strip_repo_markers(root)
    _prune_moved_dirs(repo_db.parent, templates)
    return True, f"moved {repo_db} to {home_db} (backup: {backups})"


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
        action = setup_ui.ask_migration(
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
        _record(state, finding, action)
        save_state(state, home)
    return notes


def ensure(
    cmd: str | None,
    args: Any,
    cwd: Path,
    home: Path | None = None,
    version: str = "",
    interactive: bool | None = None,
) -> dict[str, Any] | None:
    """First-run setup and upgrade review; never blocks agent commands."""
    if os.environ.get(NO_SETUP_ENV, "").strip():
        return None
    if cmd in SKIP_COMMANDS or getattr(args, "version", False):
        return None
    home = home or Path.home()
    state = load_state(home)
    explicit = str(getattr(args, "db", "") or os.environ.get("LAZYPLAN_DB", "") or "") or None
    findings = detect_findings(cwd, home, state, explicit)
    version_changed = state.last_version != (version or "")
    first = not state.last_version
    if not first and not version_changed and not findings:
        return None
    human = cmd in HUMAN_COMMANDS
    can_prompt = (
        setup_ui.stdin_tty() and sys.stderr.isatty() if interactive is None else interactive
    )
    if explicit:
        # An explicit database is a caller-owned context: never write layout,
        # skills, or state around it.
        return None
    if human and can_prompt and first:
        return run_wizard(cwd, home, state, version, json_mode=bool(getattr(args, "json", False)))
    choice = choice_from_args(args, cwd, home, state)
    root = find_repo_root(cwd)
    result = apply_choice(choice, root, home, version)
    if human and findings:
        fresh = load_state(home)
        review_findings(
            findings,
            fresh,
            home,
            root,
            write=sys.stderr,
            color=setup_ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
            allow_prompt=can_prompt,
            json_mode=bool(getattr(args, "json", False)),
        )
    return result


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
        if repo_db.is_file():
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
    out.extend(_legacy_db_findings(home))
    out.extend(_stale_skill_findings(home))
    return out


def _repo_resource_findings(root: Path, state: SetupState) -> list[Finding]:
    """Repo templates/config/skills ignored while plans live at home."""
    if state.placement != HOME:
        return []
    plan_dir = root / ".agents" / "lazyplan"
    shared = plan_dir / "lazyplan.db"
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


def _legacy_db_findings(home: Path) -> list[Finding]:
    """Old per-agent databases that resolution no longer reads."""
    home_db = shared_db_path(home)
    out: list[Finding] = []
    for path in skills.agent_local_db_candidates(home):
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
            text = path.read_text()
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
