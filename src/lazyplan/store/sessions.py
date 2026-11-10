"""Store methods for sessions and event tagging."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from ..core.entities import Session
from ..core.policies.sessions import (
    IDLE_AFTER_SECS,
    auto_close_summary,
    normalize_handoff,
    normalize_phase,
    normalize_summary,
    parse_session_id,
    supersede_summary,
)
from .base import StoreBase
from .session_pointer import (
    SESSION_ENV,
    clear_pointer,
    read_pointer,
    write_pointer,
)


class SessionsMixin(StoreBase):
    """Session persistence and active-session resolution."""

    @staticmethod
    def _row_to_session(r: sqlite3.Row) -> Session:
        """Row to Session."""
        plan_id = r["plan_id"]
        return Session(
            id=int(r["id"]),
            actor=str(r["actor"]),
            plan_id=int(plan_id) if plan_id is not None else None,
            repo_path=str(r["repo_path"] or ""),
            branch=str(r["branch"] or ""),
            started_at=float(r["started_at"]),
            ended_at=float(r["ended_at"] or 0),
            summary=str(r["summary"] or ""),
            handoff=str(r["handoff"] or ""),
            phase=str(r["phase"] or "working"),
            last_seen_at=float(r["last_seen_at"] or 0),
            host=str(r["host"] or ""),
            auto_closed=bool(r["auto_closed"]),
        )

    def _open_session(self, actor: str, repo_path: str) -> Session | None:
        """Newest unended session for one actor and checkout."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE actor=? AND repo_path=? AND ended_at=0"
                " ORDER BY id DESC LIMIT 1",
                (actor, repo_path),
            ).fetchone()
        return self._row_to_session(row) if row is not None else None

    def _resolve_session(self, actor: str) -> Session | None:
        """Open session from the env override, else the checkout pointer."""
        raw = os.environ.get(SESSION_ENV, "").strip()
        if raw:
            try:
                session_id = parse_session_id(raw)
            except ValueError:
                session_id = 0
            if session_id:
                row = self.get_session(session_id)
                if row is not None and not row.ended and row.actor == actor:
                    return row
        repo_path = self.checkout_path()
        pointer_id = read_pointer(self.path, actor, repo_path)
        if pointer_id is None:
            return None
        row = self.get_session(pointer_id)
        if row is None or row.ended or row.actor != actor:
            return None
        return row

    def _resolve_session_id(self, actor: str) -> int | None:
        """Active session id for *actor*, cached for one CLI invocation."""
        if actor not in self._session_cache:
            row = self._resolve_session(actor)
            self._session_cache[actor] = row.id if row is not None else None
        return self._session_cache[actor]

    def start_session(
        self,
        actor: str,
        plan_id: int | None = None,
        repo_path: str = "",
        branch: str = "",
        note: str = "",
        force: bool = False,
        now: float | None = None,
        host: str = "",
        phase: str = "working",
    ) -> tuple[Session, Session | None]:
        """Open a session; idle ones in this checkout are closed first."""
        stamp = time.time() if now is None else now
        repo = (
            str(Path(repo_path).expanduser().resolve())
            if repo_path.strip()
            else self.checkout_path()
        )
        self.reap_idle_sessions(now=stamp, repo_path=repo)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if plan_id is not None:
                found = conn.execute("SELECT id FROM plans WHERE id=?", (plan_id,)).fetchone()
                if found is None:
                    raise KeyError(f"plan #{plan_id} not found")
            previous = self._open_session(actor, repo)
            if previous is not None and not force:
                raise ValueError(f"session S{previous.id} is already open; end it or pass --force")
            cur = conn.execute(
                "INSERT INTO sessions"
                " (actor, plan_id, repo_path, branch, started_at, phase, last_seen_at, host)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    actor,
                    plan_id,
                    repo,
                    branch.strip(),
                    stamp,
                    normalize_phase(phase),
                    stamp,
                    str(host)[:64],
                ),
            )
            session_id = int(cur.lastrowid or 0)
            if previous is not None:
                conn.execute(
                    "UPDATE sessions SET ended_at=?, summary=? WHERE id=?",
                    (stamp, supersede_summary(previous.id, session_id), previous.id),
                )
            detail = f"session S{session_id} started"
            if note.strip():
                detail += f": {note.strip()[:120]}"
            self.log(actor, "session", "start", detail, session_id=session_id)
        write_pointer(self.path, actor, repo, session_id, stamp)
        if previous is not None:
            previous = self.get_session(previous.id)
        self._session_cache.pop(actor, None)
        row = self.get_session(session_id)
        assert row is not None
        return row, previous

    def end_session(
        self,
        session_id: int,
        actor: str,
        summary: str = "",
        handoff: str = "",
        now: float | None = None,
        auto: bool = False,
    ) -> Session:
        """Close one session with a summary and handoff."""
        stamp = time.time() if now is None else now
        body = normalize_summary(summary)
        next_step = normalize_handoff(handoff)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise KeyError(f"session S{session_id} not found")
            if int(row["ended_at"] or 0) > 0:
                raise ValueError(f"session S{session_id} has already ended")
            repo = str(row["repo_path"] or "")
            owner = str(row["actor"])
            action = "auto-close" if auto else "end"
            self.log(
                actor,
                "session",
                action,
                f"session S{session_id} {action}d",
                session_id=session_id,
            )
            conn.execute(
                "UPDATE sessions SET ended_at=?, summary=?, handoff=?, auto_closed=? WHERE id=?",
                (stamp, body, next_step, int(auto), session_id),
            )
        clear_pointer(self.path, owner, repo, session_id=session_id)
        self._session_cache.pop(owner, None)
        self._session_cache.pop(actor, None)
        ended = self.get_session(session_id)
        assert ended is not None
        return ended

    def touch_session(
        self,
        session_id: int,
        phase: str | None = None,
        host: str = "",
        now: float | None = None,
    ) -> Session | None:
        """Refresh one open session's heartbeat and optional phase."""
        stamp = time.time() if now is None else now
        sets = ["last_seen_at=?"]
        params: list[object] = [stamp]
        if phase is not None:
            sets.append("phase=?")
            params.append(normalize_phase(phase))
        if host:
            sets.append("host=?")
            params.append(str(host)[:64])
        params.append(session_id)
        with self._connect() as conn:
            row = conn.execute("SELECT ended_at FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row is None or int(row["ended_at"] or 0) > 0:
                return None
            conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", params)
        return self.get_session(session_id)

    def open_session_for(
        self,
        repo_path: str,
        host: str = "",
        actor: str = "",
    ) -> Session | None:
        """Newest open session in one checkout, preferring a matching host."""
        base = "SELECT * FROM sessions WHERE ended_at=0 AND repo_path=?"
        if host:
            with self._connect() as conn:
                row = conn.execute(
                    base + " AND host=? ORDER BY started_at DESC, id DESC LIMIT 1",
                    (repo_path, host),
                ).fetchone()
            if row is not None:
                return self._row_to_session(row)
        sql = base
        params: list[object] = [repo_path]
        if actor:
            sql += " AND actor=?"
            params.append(actor)
        sql += " ORDER BY started_at DESC, id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_session(row) if row is not None else None

    def reap_idle_sessions(
        self,
        now: float | None = None,
        idle_after: float = IDLE_AFTER_SECS,
        repo_path: str = "",
    ) -> list[Session]:
        """Close open sessions whose heartbeat is older than *idle_after*."""
        stamp = time.time() if now is None else now
        cutoff = stamp - max(idle_after, 0.0)
        sql = "SELECT * FROM sessions WHERE ended_at=0"
        params: list[object] = []
        if repo_path:
            sql += " AND repo_path=?"
            params.append(repo_path)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        closed: list[Session] = []
        for row in rows:
            anchor = float(row["last_seen_at"] or row["started_at"] or 0.0)
            if anchor >= cutoff:
                continue
            session_id = int(row["id"])
            owner = str(row["actor"])
            repo = str(row["repo_path"] or "")
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET ended_at=?, summary=?, auto_closed=1 WHERE id=?",
                    (stamp, auto_close_summary(stamp - anchor), session_id),
                )
                self.log(
                    owner,
                    "session",
                    "auto-close",
                    f"session S{session_id} auto-closed after idle",
                    session_id=session_id,
                )
            clear_pointer(self.path, owner, repo, session_id=session_id)
            ended = self.get_session(session_id)
            if ended is not None:
                closed.append(ended)
        self._session_cache.clear()
        return closed

    def get_session(self, session_id: int) -> Session | None:
        """One session by id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return self._row_to_session(row) if row is not None else None

    def active_session(self, actor: str) -> Session | None:
        """The session this actor's writes would tag, if any."""
        session_id = self._resolve_session_id(actor)
        return None if session_id is None else self.get_session(session_id)

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
    ) -> list[Session]:
        """Recent sessions, newest first, with optional actor and plan filters."""
        sql = "SELECT * FROM sessions"
        clauses: list[str] = []
        params: list[object] = []
        if actor:
            clauses.append("actor=?")
            params.append(actor)
        if plan_id is not None:
            clauses.append("plan_id=?")
            params.append(plan_id)
        if open_only:
            clauses.append("ended_at=0")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC, id DESC LIMIT ?"
        params.append(max(int(limit), 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_session(row) for row in rows]

    def latest_ended_session(
        self,
        plan_id: int | None = None,
        actor: str = "",
        repo_path: str = "",
    ) -> Session | None:
        """Most recently ended session for a plan or checkout."""
        sql = "SELECT * FROM sessions WHERE ended_at > 0"
        params: list[object] = []
        if plan_id is not None:
            sql += " AND plan_id=?"
            params.append(plan_id)
        if actor:
            sql += " AND actor=?"
            params.append(actor)
        if repo_path:
            sql += " AND repo_path=?"
            params.append(repo_path)
        sql += " ORDER BY ended_at DESC, id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_session(row) if row is not None else None

    def events_for_session(self, session_id: int, limit: int = 50) -> list[dict]:
        """Newest events tagged with one session."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, max(int(limit), 1)),
            ).fetchall()
        return [dict(row) for row in rows]

    def session_counts(self, session_id: int) -> dict[str, int]:
        """Event counts by action for one session."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT action, COUNT(*) AS n FROM events WHERE session_id=?"
                " GROUP BY action ORDER BY action",
                (session_id,),
            ).fetchall()
        return {str(row["action"]): int(row["n"]) for row in rows}
