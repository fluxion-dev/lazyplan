"""SQLite persistence core: connection, events, and shared types."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from lazyplan.infrastructure.checkout import PathAdapter
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
from ..core.ports.paths import PathPort
from ..core.serialization import to_payload
from .migrate import migrate

if TYPE_CHECKING:
    from typing import Protocol

    from ..core.entities import PlanChange, Task
    from ..core.ports.app import AppPort

    class _StoreContract(AppPort, Protocol):
        """The assembled Store: public capabilities plus cross-mixin helpers."""

        @staticmethod
        def _opt(r: sqlite3.Row, keys: set[str], name: str) -> str: ...

        def _row_to_task(self, r: sqlite3.Row) -> Task: ...

        def _plan_for_kind(self, kind: str, obj_id: int) -> int | None: ...

        def _record_scope_change(
            self,
            plan_id: int,
            kind: str,
            obj_id: int,
            action: str,
            field: str = "",
            reason: str = "",
            detail: str = "",
            actor: str = "human",
        ) -> PlanChange | None: ...

        @staticmethod
        def _delete_entity_repos(conn: sqlite3.Connection, kind: str, obj_id: int) -> None: ...

        def _parent_exists(self, parent_kind: str, parent_id: int) -> bool: ...

else:
    _StoreContract = object


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


_K = TypeVar("_K")
_V = TypeVar("_V")


class StoreBase(_StoreContract):
    def __init__(self, path: str | Path | None = None, paths: PathPort | None = None) -> None:
        self.path = resolve_db_path(path)
        self.paths = paths or PathAdapter()
        self._local = threading.local()
        try:
            if Path(self.path).expanduser() == shared_db_path():
                seed_shared_db(self.path)
        except OSError:
            pass
        ensure_plan_dir(self.path)
        with self._connect() as conn:
            migrate(conn)
        with sqlite3.connect(str(self.path), timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode = WAL")

    @property
    def db_path(self) -> str:
        """Database path as text for ports and template lookups."""
        return str(self.path)

    def repo_root(self, cwd: str = ".") -> str | None:
        """Enclosing git root for *cwd*, or None."""
        return self.paths.repo_root(cwd)

    def checkout_path(self, cwd: str | None = None) -> str:
        """Repo root for *cwd*, else the resolved working directory."""
        return self.paths.checkout_path(cwd)

    def resolve_repo_path(self, path: str) -> str:
        """Absolute path without case folding."""
        return self.paths.resolve_repo_path(path)

    def normalize_repo_path(self, path: str) -> str:
        """Absolute, case-folded path for equality checks."""
        return self.paths.normalize_repo_path(path)

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
        conn = sqlite3.connect(str(self.path), timeout=5.0)
        self._local.conn = conn
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            self._local.conn = None
            conn.close()

    def _grouped(
        self,
        sql: str,
        params: Sequence[object],
        make: Callable[[sqlite3.Row], _V],
        key: Callable[[sqlite3.Row], _K],
    ) -> dict[_K, list[_V]]:
        """Rows mapped by *make* and grouped under the row's *key*, in read order."""
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: dict[_K, list[_V]] = {}
        for row in rows:
            out.setdefault(key(row), []).append(make(row))
        return out

    def _indexed(
        self,
        sql: str,
        params: Sequence[object],
        make: Callable[[sqlite3.Row], _V],
        key: Callable[[sqlite3.Row], _K],
    ) -> dict[_K, _V]:
        """One value per key, for a read with at most one row per key."""
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {key(row): make(row) for row in rows}

    def _latest_ended(
        self,
        table: str,
        ended: str,
        actor_column: str,
        make: Callable[[sqlite3.Row], _V],
        plan_id: int | None = None,
        actor: str = "",
        repo_path: str = "",
    ) -> _V | None:
        """Newest ended, unarchived row of *table* for a plan, actor, or checkout."""
        sql = f"SELECT * FROM {table} WHERE {ended} AND archived_at = 0"
        params: list[object] = []
        if plan_id is not None:
            sql += " AND plan_id=?"
            params.append(plan_id)
        if actor:
            sql += f" AND {actor_column}=?"
            params.append(actor)
        if repo_path:
            sql += " AND repo_path=?"
            params.append(repo_path)
        sql += " ORDER BY ended_at DESC, id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return make(row) if row is not None else None

    def log(
        self,
        actor: str,
        kind: str,
        action: str,
        detail: str = "",
        session_id: int | None = None,
        now: float | None = None,
    ) -> None:
        """Append an event row; history rows keep their original session tag."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail, session_id)"
                " VALUES (?,?,?,?,?,?)",
                (stamp, _actor(actor), kind, action, detail[:500], session_id),
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
        """Structural poll key: counts, max ids, and the events watermark.

        Session heartbeats and database-file mtimes are deliberately absent:
        a live-only write must never look like a plan change. Any structural
        edit through the store appends an event, so the watermark covers
        status, title, and description updates that leave ids unchanged.
        """
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
        return (
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
        )

    def live_fingerprint(self) -> tuple:
        """Live poll key: agent rows, newest update, and terminal count.

        This changes on every agent transition so the tracker can repaint
        while the plan tree stays untouched.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) c,"
                    " COALESCE(MAX(id),0) newest,"
                    " COALESCE(MAX(updated_at),0) seen,"
                    " COALESCE(SUM(CASE WHEN ended_at>0 THEN 1 ELSE 0 END),0) ended"
                    " FROM agents"
                ).fetchone()
        except Exception:
            return (0, 0, 0.0, 0)
        return (int(row["c"]), int(row["newest"]), float(row["seen"]), int(row["ended"]))


_ser = to_payload
