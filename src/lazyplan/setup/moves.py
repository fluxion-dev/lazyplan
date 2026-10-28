"""Setup moves."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..repo import (
    CONFIG_NAME,
    TEMPLATES_DIR_NAME,
    is_repo_plan_dir,
    shared_db_path,
)
from . import layout
from .state import plans_in


def _move_sources(repo_db: Path, root: Path | None) -> list[Path]:
    """Every file a move touches, in backup order."""
    sources = [repo_db]
    config = repo_db.parent / CONFIG_NAME
    templates = repo_db.parent / TEMPLATES_DIR_NAME
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
        layout._strip_agents(agents)
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        layout._strip_gitignore(gitignore)


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
    root = repo_root or (repo_db.parent.parent.parent if is_repo_plan_dir(repo_db.parent) else None)
    backups = layout.new_backup_dir(home)
    for source in _move_sources(repo_db, root):
        layout.backup_file(backups, source)
    if home_db.is_file():
        layout.backup_file(backups, home_db)
        home_db.unlink()
    home_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(repo_db), str(home_db))
    templates = repo_db.parent / TEMPLATES_DIR_NAME
    config = repo_db.parent / CONFIG_NAME
    if templates.is_dir():
        _merge_templates(templates, home_db.parent / TEMPLATES_DIR_NAME)
    if config.is_file():
        config.unlink()
    if root is not None:
        _strip_repo_markers(root)
    _prune_moved_dirs(repo_db.parent, templates)
    return True, f"moved {repo_db} to {home_db} (backup: {backups})"
