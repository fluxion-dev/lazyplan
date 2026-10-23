"""Resolve and repair the resources `lpui init` installs.

One layout decides where the database, config, templates, skills,
AGENTS.md pointer, and gitignore entries belong. Nothing here writes
unless `apply_repairs` or `apply_layout` is called.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .repo import (
    CONFIG_NAME,
    DB_NAME,
    PLAN_DIR,
    is_repo_plan_dir,
    legacy_plan_dir,
    move_legacy_plan_dir,
    repo_plan_db_path,
    shared_db_path,
    shared_home,
)
from .skills import (
    AGENTS_MARK_BEGIN,
    AGENTS_MARK_END,
    SkillPlan,
    render_skill,
)

STORAGE_HOME = "home"
STORAGE_REPO = "repo"
STORAGE_EXPLICIT = "explicit"


@dataclass(frozen=True)
class InitLayout:
    """Everything init is allowed to create, resolved before any write."""

    storage: str
    repo_root: Path | None
    db: Path
    plan_dir: Path
    config: Path | None
    templates_dir: Path
    skill_plan: SkillPlan
    agents_md: Path | None
    gitignore_entries: tuple[str, ...]
    explicit: bool
    home: Path
    legacy_dir: Path | None = None

    def to_dict(self) -> dict:
        """JSON-safe layout summary."""
        return {
            "storage": self.storage,
            "db": str(self.db),
            "plan_dir": str(self.plan_dir),
            "config": str(self.config) if self.config else None,
            "templates": str(self.templates_dir),
            "skills": self.skill_plan.to_dict(),
            "agents_md": str(self.agents_md) if self.agents_md else None,
            "gitignore": list(self.gitignore_entries),
        }


@dataclass(frozen=True)
class RepairAction:
    """One safe repair step."""

    action: str  # move | backup | strip | remove
    source: Path
    target: Path | None
    reason: str


@dataclass
class RepairPlan:
    """What a repair would do, and whether init must stop instead."""

    actions: list[RepairAction] = field(default_factory=list)
    stop: str | None = None
    repo_root: Path | None = None
    home: Path | None = None

    def to_dict(self) -> dict:
        return {
            "actions": [
                {
                    "action": action.action,
                    "source": str(action.source),
                    "target": str(action.target) if action.target else None,
                    "reason": action.reason,
                }
                for action in self.actions
            ],
            "stop": self.stop,
        }


def _explicit_db(args: Namespace) -> Path | None:
    flag = getattr(args, "db", None)
    if flag:
        return Path(str(flag)).expanduser()
    env = os.environ.get("LAZYPLAN_DB", "").strip()
    return Path(env).expanduser() if env else None


def _repo_storage(args: Namespace, repo_root: Path | None) -> bool:
    if repo_root is None:
        return False
    scope = str(getattr(args, "skills_scope", "") or "").strip()
    return bool(getattr(args, "team", False)) or scope in ("project", "both")


def _gitignore_entries(
    repo_root: Path | None,
    plan_dir: Path,
    skill_files: list[Path],
) -> tuple[str, ...]:
    if repo_root is None:
        return ()
    entries: list[str] = []
    try:
        rel = plan_dir.expanduser().relative_to(repo_root.expanduser())
    except ValueError:
        rel = None
    if rel is not None and str(rel) != ".":
        entries.append(rel.as_posix() + "/")
    for path in skill_files:
        try:
            rel = path.expanduser().relative_to(repo_root.expanduser())
        except ValueError:
            continue
        entries.append(rel.parent.as_posix() + "/")
    return tuple(dict.fromkeys(entries))


def resolve(
    args: Namespace,
    repo_root: Path | None,
    skill_plan: SkillPlan,
    home: Path | None = None,
) -> InitLayout:
    """Resolve every destination without creating a file or directory."""
    home = home or Path.home()
    explicit_db = _explicit_db(args)
    if explicit_db is not None:
        storage = STORAGE_EXPLICIT
        db = explicit_db
    elif _repo_storage(args, repo_root):
        storage = STORAGE_REPO
        assert repo_root is not None
        db = repo_plan_db_path(repo_root)
    else:
        storage = STORAGE_HOME
        db = shared_db_path(home)
    plan_dir = db.parent
    config = plan_dir / CONFIG_NAME if is_repo_plan_dir(plan_dir) else None
    return InitLayout(
        storage=storage,
        repo_root=repo_root,
        db=db,
        plan_dir=plan_dir,
        config=config,
        templates_dir=plan_dir / "templates",
        skill_plan=skill_plan,
        agents_md=skill_plan.agents_md,
        gitignore_entries=(
            _gitignore_entries(repo_root, plan_dir, skill_plan.skill_files)
            if storage == STORAGE_REPO
            else ()
        ),
        explicit=storage == STORAGE_EXPLICIT,
        home=home,
        legacy_dir=(
            legacy_plan_dir(repo_root)
            if storage == STORAGE_REPO
            and repo_root is not None
            and legacy_plan_dir(repo_root).is_dir()
            else None
        ),
    )


def db_has_plans(path: Path) -> bool:
    """Read-only check: does this SQLite file contain at least one plan?"""
    if not path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) FROM plans").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(row and int(row[0]) > 0)


def _repo_skill_dirs(repo_root: Path) -> list[Path]:
    return [
        repo_root / ".agents/skills/lazyplan",
        repo_root / ".opencode/skills/lazyplan",
        repo_root / ".claude/skills/lazyplan",
        repo_root / ".gemini/skills/lazyplan",
        repo_root / ".cursor/skills/lazyplan",
    ]


def _generated_skill(path: Path) -> bool:
    skill = path / "SKILL.md"
    try:
        return skill.is_file() and skill.read_text() == render_skill()
    except OSError:
        return False


def _agents_block(text: str) -> tuple[str, bool]:
    if AGENTS_MARK_BEGIN not in text or AGENTS_MARK_END not in text:
        return text, False
    before, _, rest = text.partition(AGENTS_MARK_BEGIN)
    _, _, after = rest.partition(AGENTS_MARK_END)
    cleaned = (before.rstrip() + "\n" + after.lstrip()).strip()
    return (cleaned + "\n") if cleaned else "", True


def _lazyplan_gitignore_lines(path: Path) -> list[str]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    return [
        line
        for line in lines
        if line.strip()
        and (
            line.strip().rstrip("/").startswith(".agents/lazyplan")
            or line.strip().rstrip("/").endswith("/skills/lazyplan")
        )
    ]


def _new_backup_dir(home: Path) -> Path:
    """Fresh timestamped backup dir under the shared home."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    return shared_home(home) / "backups" / stamp


def _existing_files(path: Path) -> list[str]:
    """Files represented by a file or directory path; read-only."""
    try:
        if path.is_file():
            return [str(path)]
        if not path.is_dir():
            return []
        return [str(child) for child in sorted(path.rglob("*")) if child.is_file()]
    except OSError:
        return []


def _repo_resources(repo: Path) -> list[str]:
    """Existing repo-owned lazyplan resources, read-only."""
    resources: list[str] = []
    plan_dir = repo / PLAN_DIR
    if plan_dir.is_dir():
        resources.extend(str(path) for path in sorted(plan_dir.rglob("*")) if path.is_file())
    for skill_dir in _repo_skill_dirs(repo):
        if skill_dir.is_dir():
            resources.append(str(skill_dir))
    agents = repo / "AGENTS.md"
    if agents.is_file():
        try:
            if AGENTS_MARK_BEGIN in agents.read_text():
                resources.append(str(agents))
        except OSError:
            pass
    gitignore = repo / ".gitignore"
    for line in _lazyplan_gitignore_lines(gitignore):
        resources.append(f"{gitignore}: {line}")
    return resources


def _expected_paths(layout: InitLayout) -> list[Path]:
    paths = [layout.db, layout.templates_dir]
    if layout.config is not None:
        paths.append(layout.config)
    if layout.agents_md is not None:
        paths.append(layout.agents_md)
    paths.extend(layout.skill_plan.skill_files)
    return paths


def _layout_resources(layout: InitLayout) -> list[str]:
    actual: list[str] = []
    for path in _expected_paths(layout):
        actual.extend(_existing_files(path))
    return list(dict.fromkeys(actual))


def notes(layout: InitLayout) -> list[str]:
    """Human notes about overrides and legacy paths; read-only."""
    out: list[str] = []
    if layout.explicit:
        out.append(f"explicit DB wins: {layout.db} (scope repairs are skipped)")
    if layout.legacy_dir is not None:
        out.append(f"legacy plan dir: {layout.legacy_dir}")
    if layout.storage == STORAGE_REPO:
        home_db = shared_db_path(layout.home)
        if home_db.is_file():
            out.append(f"home DB left untouched: {home_db}")
    return out


def inventory(layout: InitLayout) -> dict:
    """Read-only expected/actual resource report for init --check and doctor."""
    repo_resources = _repo_resources(layout.repo_root) if layout.repo_root is not None else []
    misplaced = list(repo_resources) if layout.storage == STORAGE_HOME else []
    return {
        "expected": layout.to_dict(),
        "layout_resources": _layout_resources(layout),
        "repo_resources": repo_resources,
        "misplaced": misplaced,
        "missing": [str(path) for path in _expected_paths(layout) if not path.exists()],
        "notes": notes(layout),
        "clean": not misplaced,
    }


def plan_repairs(layout: InitLayout) -> RepairPlan:
    """Plan safe repairs for a home-scoped init with repo leftovers."""
    if layout.storage != STORAGE_HOME or layout.repo_root is None:
        return RepairPlan()
    repo = layout.repo_root
    plan = RepairPlan(repo_root=repo, home=layout.home)
    plan_dir = repo / PLAN_DIR
    repo_db = plan_dir / DB_NAME
    if repo_db.is_file():
        repo_has_plans = db_has_plans(repo_db)
        home_has_plans = db_has_plans(layout.db)
        if repo_has_plans and home_has_plans:
            plan.actions.append(
                RepairAction(
                    "backup",
                    repo_db,
                    None,
                    "home DB already has plans; repo DB left in place",
                )
            )
            plan.stop = (
                f"both databases contain plans: {repo_db} and {layout.db}. "
                f"Export one with `lpui --db {repo_db} export --format json` and "
                f"import it into the home DB before removing the repo copy."
            )
            return plan
        if not repo_has_plans:
            plan.actions.append(
                RepairAction("remove", repo_db, None, "empty repo DB removed after backup")
            )
        else:
            if layout.db.is_file():
                plan.actions.append(
                    RepairAction(
                        "backup",
                        layout.db,
                        None,
                        "home DB has no plans; back it up before the repo DB replaces it",
                    )
                )
            plan.actions.append(RepairAction("move", repo_db, layout.db, "move repo DB home"))
    config = plan_dir / CONFIG_NAME
    if config.is_file():
        plan.actions.append(RepairAction("remove", config, None, "remove repo config"))
    templates = plan_dir / "templates"
    if templates.is_dir():
        for path in sorted(templates.glob("*")):
            if not path.is_file():
                continue
            target = layout.templates_dir / path.name
            if target.exists():
                plan.actions.append(
                    RepairAction("remove", path, None, "home template already exists")
                )
            else:
                plan.actions.append(RepairAction("move", path, target, "move template home"))
    for skill_dir in _repo_skill_dirs(repo):
        if skill_dir.is_dir() and _generated_skill(skill_dir):
            plan.actions.append(
                RepairAction("remove", skill_dir, None, "remove generated repo skill")
            )
    agents = repo / "AGENTS.md"
    if agents.is_file():
        try:
            text = agents.read_text()
        except OSError:
            text = ""
        _, found = _agents_block(text)
        if found:
            plan.actions.append(RepairAction("strip", agents, None, "remove lazyplan AGENTS block"))
    gitignore = repo / ".gitignore"
    if _lazyplan_gitignore_lines(gitignore):
        plan.actions.append(
            RepairAction("strip", gitignore, None, "remove lazyplan .gitignore entries")
        )
    return plan


def _backup_path(backup_dir: Path, source: Path) -> Path:
    try:
        rel = source.relative_to(source.anchor)
    except ValueError:
        rel = Path(source.name)
    return backup_dir / rel


def _backup_file(backup_dir: Path, source: Path) -> Path:
    """Copy one file or directory into the backup tree and return its path."""
    backup = _backup_path(backup_dir, source)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, backup)
    else:
        shutil.copy2(source, backup)
    return backup


def _strip_agents(source: Path) -> bool:
    """Remove only the marked lazyplan block; delete a file left with just the heading."""
    cleaned, found = _agents_block(source.read_text())
    if not found:
        return False
    if cleaned.strip() in ("", "# Agent instructions"):
        source.unlink()
    else:
        source.write_text(cleaned)
    return True


def _strip_gitignore(source: Path) -> None:
    drop = set(_lazyplan_gitignore_lines(source))
    lines = [line for line in source.read_text().splitlines() if line.strip() not in drop]
    if lines:
        source.write_text("\n".join(lines) + "\n")
    else:
        source.unlink()


def _apply_move(action: RepairAction, backup_dir: Path, backup: Path) -> dict:
    assert action.target is not None
    target = action.target
    target_backup = str(_backup_file(backup_dir, target)) if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(action.source), str(target))
    return {
        "action": "move",
        "source": str(action.source),
        "target": str(target),
        "backup": str(backup),
        "target_backup": target_backup,
    }


def _apply_remove(action: RepairAction, backup: Path) -> dict:
    source = action.source
    if action.action == "remove":
        if source.is_dir():
            shutil.rmtree(source)
        elif source.is_file():
            source.unlink()
    return {"action": action.action, "source": str(source), "backup": str(backup)}


def _apply_strip(action: RepairAction, backup: Path) -> dict:
    if action.source.name == "AGENTS.md":
        _strip_agents(action.source)
    else:
        _strip_gitignore(action.source)
    return {"action": "strip", "source": str(action.source), "backup": str(backup)}


def _apply_action(action: RepairAction, backup_dir: Path) -> dict | None:
    if not action.source.exists():
        return None
    backup = _backup_file(backup_dir, action.source)
    if action.action == "move" and action.target is not None:
        return _apply_move(action, backup_dir, backup)
    if action.action in ("remove", "backup"):
        return _apply_remove(action, backup)
    if action.action == "strip":
        return _apply_strip(action, backup)
    return None


def apply_repairs(plan: RepairPlan, backup_dir: Path | None = None) -> dict:
    """Apply a repair plan, moving every removed/changed file into a backup."""
    if not plan.actions:
        return {"actions": [], "backup_dir": None, "stop": plan.stop}
    backup_dir = backup_dir or _new_backup_dir(plan.home or Path.home())
    done: list[dict] = []
    for action in plan.actions:
        result = _apply_action(action, backup_dir)
        if result is not None:
            done.append(result)
    if plan.repo_root is not None:
        _cleanup_empty_dirs(plan.repo_root)
    return {"actions": done, "backup_dir": str(backup_dir), "stop": plan.stop}


def _cleanup_empty_dirs(repo_root: Path) -> None:
    """Remove empty lazyplan skill/plan dirs after a repair; keep other content."""
    candidates = [
        repo_root / ".agents/lazyplan/templates",
        repo_root / ".agents/lazyplan",
        repo_root / ".agents/skills/lazyplan",
        repo_root / ".agents/skills",
        repo_root / ".agents",
    ]
    for tool in (".opencode", ".claude", ".gemini", ".cursor"):
        candidates.extend(
            [repo_root / tool / "skills/lazyplan", repo_root / tool / "skills", repo_root / tool]
        )
    for path in candidates:
        try:
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def apply_layout(
    layout: InitLayout,
    *,
    interactive: bool = False,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> dict:
    """Create only the resources in the resolved layout."""
    from .templates import run_template_setup

    legacy: dict | None = None
    if (
        layout.legacy_dir is not None
        and layout.legacy_dir.is_dir()
        and not layout.plan_dir.exists()
    ):
        backup = _backup_file(_new_backup_dir(layout.home), layout.legacy_dir)
        moved = move_legacy_plan_dir(layout.repo_root) if layout.repo_root else None
        legacy = {"moved": str(moved) if moved is not None else None, "backup": str(backup)}
    if layout.config is not None:
        layout.config.parent.mkdir(parents=True, exist_ok=True)
        if not layout.config.exists():
            layout.config.write_text(
                json.dumps(
                    {"version": 1, "db": DB_NAME, "created": datetime.now(UTC).isoformat()},
                    indent=2,
                )
                + "\n"
            )
    summary = run_template_setup(
        layout.plan_dir,
        interactive=interactive,
        read=read,
        write=write,
    )
    return {"templates": summary, "legacy": legacy}
