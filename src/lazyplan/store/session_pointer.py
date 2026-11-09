"""Resolve and persist the active session pointer beside the database."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SESSION_ENV = "LAZYPLAN_SESSION"
SESSION_DIR = "sessions"


def _key(actor: str, repo_path: str) -> str:
    """Stable short key for one actor in one checkout."""
    raw = f"{actor}\0{repo_path}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def pointer_path(db_path: str | Path, actor: str, repo_path: str | Path) -> Path:
    """Pointer file for an actor and checkout, next to the database."""
    return Path(db_path).expanduser().parent / SESSION_DIR / f"{_key(actor, str(repo_path))}.json"


def read_pointer(db_path: str | Path, actor: str, repo_path: str | Path) -> int | None:
    """Session id stored for this actor and checkout, or None."""
    path = pointer_path(db_path, actor, repo_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("actor", "")) != actor:
        return None
    session_id = data.get("id")
    if not isinstance(session_id, int) or session_id <= 0:
        return None
    return session_id


def write_pointer(
    db_path: str | Path,
    actor: str,
    repo_path: str | Path,
    session_id: int,
    started_at: float,
) -> None:
    """Atomically record the active session for this actor and checkout."""
    path = pointer_path(db_path, actor, repo_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": int(session_id),
        "actor": actor,
        "repo_path": str(repo_path),
        "started_at": float(started_at),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def clear_pointer(
    db_path: str | Path,
    actor: str,
    repo_path: str | Path,
    session_id: int | None = None,
) -> bool:
    """Remove the pointer, but only when it still names *session_id*."""
    path = pointer_path(db_path, actor, repo_path)
    if session_id is not None:
        current = read_pointer(db_path, actor, repo_path)
        if current is not None and current != session_id:
            return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True
