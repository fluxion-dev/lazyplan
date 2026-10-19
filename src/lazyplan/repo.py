"""Repo scoping: a lazyplan DB lives with the code it plans.

Resolution order for the DB path:
  1. explicit `--db PATH`
  2. `$LAZYPLAN_DB`
  3. enclosing git repo root + `.lazyplan/lazyplan.db` (created on demand;
     a legacy `.plan/` dir keeps resolving until `lpui init` moves it)
  4. global fallback `~/.local/share/lazyplan/lazyplan.db`

`lpui init` marks a repo as planned: ensures `.lazyplan/` + config + schema.
Stdlib only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

PLAN_DIR = ".lazyplan"
LEGACY_PLAN_DIR = ".plan"
DB_NAME = "lazyplan.db"
CONFIG_NAME = "config.json"


def _git_toplevel(cwd: str | Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    root = out.stdout.strip()
    return Path(root) if root else None


def find_repo_root(cwd: str | Path = ".") -> Path | None:
    """Enclosing git repo root, or None. Tries git CLI, falls back to `.git` walk."""
    root = _git_toplevel(cwd)
    if root is not None:
        return root
    cur = Path(cwd).expanduser().resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
    return None


def global_db_path() -> Path:
    """XDG-based global fallback DB path."""
    xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(xdg) / "lazyplan" / DB_NAME


def legacy_plan_dir(root: str | Path) -> Path:
    """Legacy plan dir, kept resolving until `lpui init` moves it."""
    return Path(root).expanduser() / LEGACY_PLAN_DIR


def resolve_db_path(explicit: str | Path | None = None, cwd: str | Path = ".") -> Path:
    """DB path: explicit --db, $LAZYPLAN_DB, repo .lazyplan (else legacy .plan), else global."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("LAZYPLAN_DB", "").strip()
    if env:
        return Path(env).expanduser()
    root = find_repo_root(cwd)
    if root is not None:
        if not (root / PLAN_DIR).is_dir() and (root / LEGACY_PLAN_DIR).is_dir():
            return root / LEGACY_PLAN_DIR / DB_NAME
        return root / PLAN_DIR / DB_NAME
    return global_db_path()


def move_legacy_plan_dir(root: str | Path) -> Path | None:
    """Move legacy `.plan/` to `.lazyplan/`; None when there is nothing safe to move."""
    root = Path(root).expanduser()
    legacy = root / LEGACY_PLAN_DIR
    primary = root / PLAN_DIR
    if not legacy.is_dir() or primary.exists():
        return None
    shutil.move(str(legacy), str(primary))
    return primary


def repo_label(db_path: str | Path) -> str:
    """Short human label for the statusbar: repo dir name or 'global'."""
    p = Path(db_path).expanduser()
    if p.parent.name in (PLAN_DIR, LEGACY_PLAN_DIR):
        return p.parent.parent.name or "repo"
    return "global"


def ensure_plan_dir(db_path: str | Path) -> Path:
    """Ensure the `.lazyplan/` dir exists; write config.json if repo-scoped. Returns dir."""
    p = Path(db_path).expanduser()
    plan_dir = p.parent
    plan_dir.mkdir(parents=True, exist_ok=True)
    if plan_dir.name == PLAN_DIR:
        cfg = plan_dir / CONFIG_NAME
        if not cfg.exists():
            cfg.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "db": DB_NAME,
                        "created": datetime.now(UTC).isoformat(),
                    },
                    indent=2,
                )
                + "\n"
            )
    return plan_dir
