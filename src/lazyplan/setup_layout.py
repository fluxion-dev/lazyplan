"""Resolve and create the resources setup installs.

One layout decides where the database, config, templates, skills,
AGENTS.md pointer, and gitignore entries belong. Nothing here writes
unless `apply_layout` is called.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
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
)

STORAGE_HOME = "home"
STORAGE_REPO = "repo"
STORAGE_EXPLICIT = "explicit"


@dataclass(frozen=True)
class SetupChoice:
    """Placement and skill selection, independent of argparse."""

    placement: str = "home"
    agents: list[str] | None = None
    skills_dir: str | None = None
    no_skills: bool = False
    explicit_db: str | None = None


@dataclass(frozen=True)
class SetupLayout:
    """Everything setup is allowed to create, resolved before any write."""

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


def resolve_choice(
    choice: SetupChoice,
    repo_root: Path | None,
    skill_plan: SkillPlan,
    home: Path | None = None,
) -> SetupLayout:
    """Resolve every destination without creating a file or directory."""
    home = home or Path.home()
    explicit_db = Path(choice.explicit_db).expanduser() if choice.explicit_db else None
    if explicit_db is not None:
        storage = STORAGE_EXPLICIT
        db = explicit_db
    elif choice.placement == "repo" and repo_root is not None:
        storage = STORAGE_REPO
        db = repo_plan_db_path(repo_root)
    else:
        storage = STORAGE_HOME
        db = shared_db_path(home)
    plan_dir = db.parent
    config = plan_dir / CONFIG_NAME if is_repo_plan_dir(plan_dir) else None
    return SetupLayout(
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


def _repo_skill_dirs(repo_root: Path) -> list[Path]:
    return [
        repo_root / ".agents/skills/lazyplan",
        repo_root / ".opencode/skills/lazyplan",
        repo_root / ".claude/skills/lazyplan",
        repo_root / ".gemini/skills/lazyplan",
        repo_root / ".cursor/skills/lazyplan",
    ]


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


def _expected_paths(layout: SetupLayout) -> list[Path]:
    paths = [layout.db, layout.templates_dir]
    if layout.config is not None:
        paths.append(layout.config)
    if layout.agents_md is not None:
        paths.append(layout.agents_md)
    paths.extend(layout.skill_plan.skill_files)
    return paths


def _layout_resources(layout: SetupLayout) -> list[str]:
    actual: list[str] = []
    for path in _expected_paths(layout):
        actual.extend(_existing_files(path))
    return list(dict.fromkeys(actual))


def notes(layout: SetupLayout) -> list[str]:
    """Human notes about overrides and legacy paths; read-only."""
    out: list[str] = []
    if layout.explicit:
        out.append(f"explicit DB wins: {layout.db} (migration review is skipped)")
    if layout.legacy_dir is not None:
        out.append(f"legacy plan dir: {layout.legacy_dir}")
    if layout.storage == STORAGE_REPO:
        home_db = shared_db_path(layout.home)
        if home_db.is_file():
            out.append(f"home DB left untouched: {home_db}")
    return out


def inventory(layout: SetupLayout) -> dict:
    """Read-only expected/actual resource report for doctor."""
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


def apply_layout(
    layout: SetupLayout,
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
