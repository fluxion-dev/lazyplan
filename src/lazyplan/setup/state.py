"""Setup state."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import textfile
from ..repo import (
    repo_plan_db_path,
    shared_home,
)
from .constants import (
    HOME,
    REPO,
    SETUP_VERSION,
    STATE_NAME,
)


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
    agents_pointer: bool = False
    agents_file: str = ""
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
            "agents_pointer": self.agents_pointer,
            "agents_file": self.agents_file,
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
            agents_pointer=bool(raw.get("agents_pointer", False)),
            agents_file=str(raw.get("agents_file", "") or ""),
            decisions=decisions if isinstance(decisions, dict) else {},
        )


def load_state(home: Path | None = None) -> SetupState:
    """Read setup state; missing or corrupt files return defaults."""
    path = state_path(home)
    try:
        raw = json.loads(textfile.read(path))
        return SetupState.from_dict(raw)
    except (OSError, ValueError, TypeError):
        return SetupState()


def save_state(state: SetupState, home: Path | None = None) -> Path:
    """Write setup state atomically and return the path."""
    path = state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    textfile.write(tmp, json.dumps(state.to_dict(), indent=2) + "\n")
    os.replace(tmp, path)
    return path


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


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")


def git_state(repo_root: Path) -> str:
    """Tracked, ignored, or untracked for the repo plan database."""
    db = repo_plan_db_path(repo_root)
    rel = db.relative_to(repo_root).as_posix()
    try:
        tracked = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch", "--", rel],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
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
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return "untracked"
    return "ignored" if ignored.returncode == 0 else "untracked"
