"""Timestamped backups under the shared home."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from .repo import shared_home


def new_backup_dir(home: Path) -> Path:
    """Fresh timestamped backup dir under the shared home."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    return shared_home(home) / "backups" / stamp


def _backup_path(backup_dir: Path, source: Path) -> Path:
    try:
        rel = source.relative_to(source.anchor)
    except ValueError:
        rel = Path(source.name)
    return backup_dir / rel


def backup_file(backup_dir: Path, source: Path) -> Path:
    """Copy one file or directory into the backup tree and return its path."""
    backup = _backup_path(backup_dir, source)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, backup)
    else:
        shutil.copy2(source, backup)
    return backup
