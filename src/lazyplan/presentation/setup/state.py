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

from lazyplan.core.policies.hooks import MODES, normalize_mode
from lazyplan.infrastructure import textfile
from lazyplan.infrastructure.repo import (
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
    hooks_enabled: bool = True
    hooks_mode: str = "strict"
    hook_files: list[str] = field(default_factory=list)
    skills_enabled: bool = True
    agents_pointer: bool = False
    agents_file: str = ""
    decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    integration_choices: dict[str, dict[str, Any]] = field(default_factory=dict)

    def effective_mode(self) -> str:
        """Installed mode, forced to off when hooks are disabled."""
        return self.hooks_mode if self.hooks_enabled else "off"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "placement": self.placement,
            "agents": list(self.agents),
            "skills_dir": self.skills_dir,
            "explicit_db": self.explicit_db,
            "last_version": self.last_version,
            "hooks": self.hooks,
            "hooks_enabled": self.hooks_enabled,
            "hooks_mode": self.hooks_mode,
            "hook_files": list(self.hook_files),
            "skills_enabled": self.skills_enabled,
            "agents_pointer": self.agents_pointer,
            "agents_file": self.agents_file,
            "decisions": self.decisions,
            "integration_choices": self.integration_choices,
        }

    @classmethod
    def from_dict(cls, raw: object) -> SetupState:
        """Tolerant parse: unknown shapes fall back to defaults."""
        if not isinstance(raw, dict):
            return cls()
        placement = raw.get("placement")
        agents = raw.get("agents")
        decisions = raw.get("decisions")
        hooks_enabled = bool(raw.get("hooks_enabled", raw.get("hooks", True)))
        stored_mode = raw.get("hooks_mode")
        hooks_mode = (
            normalize_mode(stored_mode, "")
            if str(stored_mode or "").strip()
            else ("strict" if hooks_enabled else "off")
        )
        if hooks_mode not in MODES:
            hooks_mode = "strict" if hooks_enabled else "off"
        return cls(
            version=int(raw.get("version", SETUP_VERSION) or SETUP_VERSION),
            placement=placement if placement in (HOME, REPO) else HOME,
            agents=[str(a) for a in agents] if isinstance(agents, list) else [],
            skills_dir=str(raw.get("skills_dir", "") or ""),
            explicit_db=bool(raw.get("explicit_db", False)),
            last_version=str(raw.get("last_version", "") or ""),
            hooks=bool(raw.get("hooks", False)),
            hooks_enabled=hooks_enabled and hooks_mode != "off",
            hooks_mode=hooks_mode,
            hook_files=[str(p) for p in raw.get("hook_files", [])]
            if isinstance(raw.get("hook_files"), list)
            else [],
            skills_enabled=bool(raw.get("skills_enabled", True)),
            agents_pointer=bool(raw.get("agents_pointer", False)),
            agents_file=str(raw.get("agents_file", "") or ""),
            decisions=decisions if isinstance(decisions, dict) else {},
            integration_choices=_integration_choices(raw.get("integration_choices")),
        )


INTEGRATION_DECISIONS = ("installed", "deferred", "never")


def _integration_choices(raw: object) -> dict[str, dict[str, Any]]:
    """Parse remembered per-item decisions, dropping unknown shapes."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item_id, value in raw.items():
        if not isinstance(item_id, str) or not isinstance(value, dict):
            continue
        decision = str(value.get("decision", "") or "")
        if decision not in INTEGRATION_DECISIONS:
            continue
        out[item_id] = {
            "decision": decision,
            "fingerprint": str(value.get("fingerprint", "") or ""),
            "version": str(value.get("version", "") or ""),
            "seen_at": str(value.get("seen_at", "") or ""),
        }
    return out


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
