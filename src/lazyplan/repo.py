"""Repo scoping: a lazyplan DB lives with the code it plans, or in the shared home.

Resolution order for the DB path:
  1. explicit `--db PATH`
  2. `$LAZYPLAN_DB`
  3. nearest enclosing team `.agents/lazyplan/` dir walking up from cwd
     (needs no git repo; a legacy `.plan/` dir never resolves by itself)
  4. shared home DB: `~/.lazyplan/lazyplan.db` on unix,
     `%LOCALAPPDATA%/lazyplan/lazyplan.db` on Windows

`lpui setup --placement repo` marks a repo as planned: ensures
`.agents/lazyplan/` + config + schema. The default placement is the shared home.
Stdlib only.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from . import textfile

PLAN_DIR = ".agents/lazyplan"
PLAN_DIR_NAME = Path(PLAN_DIR).name
LEGACY_PLAN_DIR = ".plan"
STALE_PLAN_DIRS = (".lazyplan", ".agents/plan")


def is_repo_plan_dir(plan_dir: str | Path) -> bool:
    """True for the repo-owned `.agents/lazyplan/` dir (not legacy, not global)."""
    p = Path(plan_dir).expanduser()
    return p.name == PLAN_DIR_NAME and p.parent.name == ".agents"


def stale_plan_dirs(root: str | Path) -> list[Path]:
    """Pre-move plan dirs, if present: ignored by resolution, reported by setup."""
    base = Path(root).expanduser()
    return [base / d for d in STALE_PLAN_DIRS if (base / d).is_dir()]


DB_NAME = "lazyplan.db"
CONFIG_NAME = "config.json"
TEMPLATES_DIR_NAME = "templates"
SHARED_DIR_NAME = ".lazyplan"
SHARED_WINDOWS_DIR_NAME = "lazyplan"


def _os_name() -> str:
    """Platform name, indirected so tests can simulate Windows on posix."""
    return os.name


def shared_home(home: str | Path | None = None) -> Path:
    """Shared home dir for the DB, config, and templates (no side effects).

    `%LOCALAPPDATA%/lazyplan` on Windows, `~/.lazyplan` elsewhere; falls
    back to `~/.lazyplan` when LOCALAPPDATA is missing or unreadable.
    """
    base_home = Path(home).expanduser() if home is not None else Path.home()
    if _os_name() == "nt" and home is None:
        base = os.environ.get("LOCALAPPDATA", "").strip()
        if base:
            try:
                return Path(base).expanduser() / SHARED_WINDOWS_DIR_NAME
            except (OSError, RuntimeError):
                pass
        return base_home / SHARED_DIR_NAME
    return base_home / SHARED_DIR_NAME


def shared_db_path(home: str | Path | None = None) -> Path:
    """Shared DB path for this user account (no side effects)."""
    return shared_home(home) / DB_NAME


def walk_up_team_db(cwd: str | Path = ".") -> Path | None:
    """Nearest enclosing team `.agents/lazyplan/` DB walking up, or None.

    Pure directory walk: needs no git repo, so nested checkouts and plain
    folders resolve the same way.
    """
    try:
        cur = Path(cwd).expanduser().resolve()
    except OSError:
        return None
    for parent in (cur, *cur.parents):
        try:
            if (parent / PLAN_DIR).is_dir():
                return parent / PLAN_DIR / DB_NAME
        except OSError:
            continue
    return None


def _git_toplevel(cwd: str | Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
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


def repo_plan_db_path(root: str | Path) -> Path:
    """Repo-shared DB path for a repo root (team mode). No side effects."""
    return Path(root).expanduser() / PLAN_DIR / DB_NAME


def legacy_plan_dir(root: str | Path) -> Path:
    """Legacy `.plan/` dir (never auto-resolved; setup offers a review)."""
    return Path(root).expanduser() / LEGACY_PLAN_DIR


def legacy_db_candidates(home: str | Path | None = None) -> list[Path]:
    """Old-location DBs eligible for one-time import into the shared home."""
    try:
        from .skills import agent_local_db_candidates
    except ImportError:
        candidates: list[Path] = []
    else:
        try:
            base = Path(home).expanduser() if home is not None else Path.home()
            candidates = agent_local_db_candidates(base)
        except OSError:
            candidates = []
    try:
        candidates.append(global_db_path())
    except OSError:
        pass
    seen: list[Path] = []
    for cand in candidates:
        if cand not in seen:
            seen.append(cand)
    return seen


def seed_shared_db(target: str | Path | None = None) -> Path | None:
    """Copy the newest legacy DB into an empty shared home; None if nothing to do.

    Never overwrites: returns None when the target already exists or when no
    legacy DB exists. Originals are left untouched (copy, not move).
    """
    dest = Path(target).expanduser() if target is not None else shared_db_path()
    try:
        if dest.is_file():
            return None
    except OSError:
        return None
    newest: Path | None = None
    newest_mtime = -1.0
    for cand in legacy_db_candidates():
        if cand == dest:
            continue
        try:
            if not cand.is_file():
                continue
            mtime = cand.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest_mtime:
            newest, newest_mtime = cand, mtime
    if newest is None:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(newest), str(dest))
    except OSError:
        return None
    return newest


def resolve_db_path(explicit: str | Path | None = None, cwd: str | Path = ".") -> Path:
    """DB path: explicit --db, $LAZYPLAN_DB, walk-up team dir, else shared home.

    Home default: without a team-initialized `.agents/lazyplan/`
    above cwd, every agent resolves the same shared home DB. Legacy
    `.plan/` dirs never resolve by themselves (setup reports them).
    """
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("LAZYPLAN_DB", "").strip()
    if env:
        return Path(env).expanduser()
    team = walk_up_team_db(cwd)
    if team is not None:
        return team
    return shared_db_path()


def move_legacy_plan_dir(root: str | Path) -> Path | None:
    """Move legacy `.plan/` to `.agents/lazyplan/`; None when there is nothing safe to move."""
    root = Path(root).expanduser()
    legacy = root / LEGACY_PLAN_DIR
    primary = root / PLAN_DIR
    if not legacy.is_dir() or primary.exists():
        return None
    primary.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(primary))
    return primary


def repo_label(db_path: str | Path) -> str:
    """Short human label for the statusbar: repo dir name or 'global'."""
    p = Path(db_path).expanduser()
    if is_repo_plan_dir(p.parent):
        return p.parent.parent.parent.name or "repo"
    if p.parent.name == LEGACY_PLAN_DIR:
        return p.parent.parent.name or "repo"
    return "global"


def ensure_plan_dir(db_path: str | Path) -> Path:
    """Ensure the `.agents/lazyplan/` dir exists; write config.json if repo-scoped. Returns dir."""
    p = Path(db_path).expanduser()
    plan_dir = p.parent
    plan_dir.mkdir(parents=True, exist_ok=True)
    if is_repo_plan_dir(plan_dir):
        cfg = plan_dir / CONFIG_NAME
        if not cfg.exists():
            textfile.write(
                cfg,
                json.dumps(
                    {
                        "version": 1,
                        "db": DB_NAME,
                        "created": datetime.now(UTC).isoformat(),
                    },
                    indent=2,
                )
                + "\n",
            )
    return plan_dir
