"""SQLite persistence core: connection, events, and shared types."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from lazyplan.infrastructure.repo import (
    ensure_plan_dir,
    resolve_db_path,
    seed_shared_db,
    shared_db_path,
)
from lazyplan.infrastructure.settings import default_actor

from ..core.errors import ClaimConflict as ClaimConflict
from ..core.errors import ClaimError as ClaimError
from ..core.errors import ClaimMissing as ClaimMissing
from ..core.serialization import to_payload
from .migrate import migrate
from .stubs import StoreStubs


def _files_json(files: tuple[str, ...] | list[str]) -> str:
    """Canonical JSON array for changed file paths."""
    seen: set[str] = set()
    out: list[str] = []
    for path in files:
        text = str(path or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return json.dumps(out, separators=(",", ":"))


def _files_tuple(payload: str) -> tuple[str, ...]:
    """Decode a stored file list, tolerating legacy or malformed values."""
    try:
        raw = json.loads(payload or "[]")
    except ValueError:
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw if isinstance(item, str) and item)


def _actor(explicit: str = "") -> str:
    """Normalize an actor name, defaulting to the login name."""
    if explicit.strip():
        return explicit.strip()[:64]
    return default_actor()


class StoreBase(StoreStubs):
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_db_path(path)
        self._local = threading.local()
        self._session_cache: dict[str, int | None] = {}
        try:
            if Path(self.path).expanduser() == shared_db_path():
                seed_shared_db(self.path)
        except OSError:
            pass
        ensure_plan_dir(self.path)
        with self._connect() as conn:
            migrate(conn)

    @property
    def db_path(self) -> str:
        """Database path as text for ports and template lookups."""
        return str(self.path)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One transactional connection for an atomic service operation."""
        with self._connect():
            yield

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One transaction on a row-factory connection, closed on exit.

        A call nested inside another on the same thread joins the outer
        transaction on the outer connection.
        """
        active = getattr(self._local, "conn", None)
        if active is not None:
            yield active
            return
        conn = sqlite3.connect(str(self.path))
        self._local.conn = conn
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            self._local.conn = None
            conn.close()

    def log(
        self,
        actor: str,
        kind: str,
        action: str,
        detail: str = "",
        session_id: int | None = None,
    ) -> None:
        """Append an event row, tagged with the active session when one exists."""
        if session_id is None:
            session_id = self._resolve_session_id(actor)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail, session_id)"
                " VALUES (?,?,?,?,?,?)",
                (time.time(), _actor(actor), kind, action, detail[:500], session_id),
            )

    def feed(self, limit: int = 20) -> list[dict]:
        """Recent events, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (max(limit, 1),)
            ).fetchall()
        return [dict(r) for r in rows]

    def events_by_action(self, *actions: str) -> list[dict]:
        """All events with one of these actions, oldest first."""
        wanted = [action for action in actions if action]
        if not wanted:
            return []
        marks = ",".join("?" for _ in wanted)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM events WHERE action IN ({marks}) ORDER BY id",
                wanted,
            ).fetchall()
        return [dict(row) for row in rows]

    def fingerprint(self) -> tuple:
        """Conflict-safe poll key: mtime + row counts + max ids."""
        try:
            mtime = os.path.getmtime(str(self.path))
        except OSError:
            mtime = 0.0
        c = self.counts()
        with self._connect() as conn:
            mp = conn.execute("SELECT COALESCE(MAX(id),0) m FROM plans").fetchone()["m"]
            ms = conn.execute("SELECT COALESCE(MAX(id),0) m FROM milestones").fetchone()["m"]
            mt = conn.execute("SELECT COALESCE(MAX(id),0) m FROM tasks").fetchone()["m"]
            me = conn.execute("SELECT COALESCE(MAX(id),0) m FROM events").fetchone()["m"]
            mc = conn.execute("SELECT COALESCE(MAX(id),0) m FROM criteria").fetchone()["m"]
            ml = conn.execute("SELECT COALESCE(MAX(id),0) m FROM vcs_links").fetchone()["m"]
            try:
                mf = conn.execute("SELECT COALESCE(MAX(id),0) m FROM forge_links").fetchone()["m"]
            except Exception:
                mf = 0
            try:
                mr = conn.execute("SELECT COALESCE(MAX(id),0) m FROM entity_repos").fetchone()["m"]
            except Exception:
                mr = 0
            try:
                mses = conn.execute("SELECT COALESCE(MAX(id),0) m FROM sessions").fetchone()["m"]
                mseen = conn.execute(
                    "SELECT COALESCE(MAX(last_seen_at),0) m FROM sessions"
                ).fetchone()["m"]
            except Exception:
                mses, mseen = 0, 0.0
        return (
            mtime,
            c["plans"],
            c["milestones"],
            c["tasks"],
            mp,
            ms,
            mt,
            me,
            mc,
            ml,
            mr,
            mf,
            mses,
            mseen,
        )


_ser = to_payload
