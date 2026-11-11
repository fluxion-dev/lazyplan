"""Resolve and persist the active session pointer beside the database."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SESSION_ENV = "LAZYPLAN_SESSION"
SESSION_DIR = "sessions"
BINDINGS_DIR = "bindings"


def _key(actor: str, repo_path: str) -> str:
    """Stable short key for one actor in one checkout."""
    raw = f"{actor}\0{repo_path}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def _binding_key(host: str, host_session: str, project: str) -> str:
    raw = f"{host}\0{host_session}\0{project}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _bindings_dir(db_path: str | Path) -> Path:
    return Path(db_path).expanduser().parent / SESSION_DIR / BINDINGS_DIR


def binding_path(db_path: str | Path, host: str, host_session: str, project: str) -> Path:
    """Binding file for one host session in one project."""
    return _bindings_dir(db_path) / f"{_binding_key(host, host_session, project)}.json"


def _read_binding_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("session_id"), int) or int(data["session_id"]) <= 0:
        return None
    return data


def read_binding(
    db_path: str | Path,
    host: str,
    host_session: str,
    project: str,
) -> dict | None:
    """Read one host-session binding, or None when missing or corrupt."""
    if not host_session:
        return None
    return _read_binding_file(binding_path(db_path, host, host_session, project))


def write_binding(
    db_path: str | Path,
    host: str,
    host_session: str,
    project: str,
    repo_path: str,
    session_id: int,
    seen_at: float,
) -> None:
    """Atomically record a host session's journal row and last-seen stamp."""
    if not host_session:
        return
    path = binding_path(db_path, host, host_session, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "host": host,
        "host_session": host_session,
        "project": project,
        "repo_path": repo_path,
        "session_id": int(session_id),
        "seen_at": float(seen_at),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def delete_binding(
    db_path: str | Path,
    host: str,
    host_session: str,
    project: str,
) -> bool:
    """Remove one binding; return whether a file was removed."""
    if not host_session:
        return False
    try:
        binding_path(db_path, host, host_session, project).unlink()
    except FileNotFoundError:
        return False
    return True


def _bindings(db_path: str | Path) -> list[dict]:
    directory = _bindings_dir(db_path)
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError:
        return []
    found: list[dict] = []
    for path in paths:
        data = _read_binding_file(path)
        if data is not None:
            found.append(data)
    return found


def bindings_for_session(db_path: str | Path, session_id: int) -> list[dict]:
    """Every host binding that still names one journal session."""
    return [item for item in _bindings(db_path) if item.get("session_id") == session_id]


def bindings_for_project(db_path: str | Path, project: str) -> list[dict]:
    """Every host binding in one project, newest last-seen first."""
    found = [item for item in _bindings(db_path) if item.get("project") == project]
    return sorted(found, key=lambda item: float(item.get("seen_at", 0)), reverse=True)



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
