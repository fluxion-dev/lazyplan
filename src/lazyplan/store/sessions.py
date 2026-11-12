"""Store methods for sessions and event tagging."""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Sequence
from pathlib import Path

from ..core.entities import Session
from ..core.policies.maintenance import check_archive_mode
from ..core.policies.sessions import (
    auto_close_summary,
    close_after_secs,
    normalize_handoff,
    normalize_phase,
    normalize_plan_source,
    normalize_summary,
    parse_session_id,
    supersede_summary,
)
from .base import StoreBase
from .session_pointer import (
    SESSION_ENV,
    bindings_for_session,
    clear_pointer,
    delete_binding,
    read_binding,
    read_pointer,
    write_binding,
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
            host_session=str(r["host_session"] or ""),
            auto_closed=bool(r["auto_closed"]),
            plan_source=str(r["plan_source"] or "auto"),
            archived_at=float(r["archived_at"] or 0),
        )

    def _open_session(self, actor: str, repo_path: str) -> Session | None:
        """Newest unended session for one actor and checkout."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE actor=? AND repo_path=? AND ended_at=0"
                " AND archived_at=0 ORDER BY id DESC LIMIT 1",
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

    def bind_session(
        self,
        host: str,
        host_session: str,
        project: str,
        repo_path: str,
        session_id: int,
        now: float | None = None,
    ) -> None:
        """Record one host session's journal row and mirror it onto the row."""
        if host_session:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE sessions SET host_session=? WHERE id=? AND host_session<>?",
                    (str(host_session)[:128], session_id, str(host_session)[:128]),
                )
        write_binding(
            self.path,
            host,
            host_session,
            project,
            repo_path,
            session_id,
            time.time() if now is None else now,
        )

    def session_for_host(
        self,
        host: str,
        host_session: str,
        project: str,
    ) -> Session | None:
        """Open row bound to one host session in this project, if any."""
        binding = read_binding(self.path, host, host_session, project)
        if binding is None:
            return None
        session = self.get_session(int(binding.get("session_id", 0)))
        if session is None or session.ended:
            return None
        return session

    def detach_host_binding(
        self,
        host: str,
        host_session: str,
        project: str,
    ) -> tuple[Session | None, bool]:
        """Remove one binding; return its row and whether it was the last one."""
        binding = read_binding(self.path, host, host_session, project)
        delete_binding(self.path, host, host_session, project)
        if binding is None:
            return None, False
        session_id = int(binding.get("session_id", 0))
        remaining = bindings_for_session(self.path, session_id)
        return self.get_session(session_id), not remaining

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
        host_session: str = "",
        phase: str = "working",
        plan_source: str = "auto",
    ) -> tuple[Session, Session | None]:
        """Open a session; manual starts idle ones in this checkout first."""
        stamp = time.time() if now is None else now
        repo = (
            str(Path(repo_path).expanduser().resolve())
            if repo_path.strip()
            else self.checkout_path()
        )
        host_session = str(host_session).strip()[:128]
        self.reap_idle_sessions(now=stamp, repo_path=repo)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if plan_id is not None:
                found = conn.execute("SELECT id FROM plans WHERE id=?", (plan_id,)).fetchone()
                if found is None:
                    raise KeyError(f"plan #{plan_id} not found")
            previous = None if host_session else self._open_session(actor, repo)
            if previous is not None and not force:
                raise ValueError(f"session S{previous.id} is already open; end it or pass --force")
            cur = conn.execute(
                "INSERT INTO sessions"
                " (actor, plan_id, repo_path, branch, started_at, phase, last_seen_at, host,"
                " host_session, plan_source)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    actor,
                    plan_id,
                    repo,
                    branch.strip(),
                    stamp,
                    normalize_phase(phase),
                    stamp,
                    str(host)[:64],
                    host_session,
                    normalize_plan_source(plan_source),
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
            self.log(actor, "session", "start", detail, session_id=session_id, now=stamp)
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
                now=stamp,
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

    def archive_sessions(
        self,
        session_ids: Sequence[int],
        actor: str = "human",
        now: float | None = None,
    ) -> int:
        """Archive ended sessions and remove their binding files.

        Open sessions are never archived. Each newly archived row writes one
        event; already archived or missing rows are skipped.
        """
        stamp = time.time() if now is None else now
        archived: list[int] = []
        with self._connect() as conn:
            for session_id in session_ids:
                session = conn.execute(
                    "SELECT actor, repo_path FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                cur = conn.execute(
                    "UPDATE sessions SET archived_at=? WHERE id=? AND ended_at>0 AND archived_at=0",
                    (stamp, session_id),
                )
                if (cur.rowcount or 0) == 0:
                    continue
                self.log(
                    actor,
                    "session",
                    "archive",
                    f"session S{session_id} archived",
                    session_id=session_id,
                    now=stamp,
                )
                if session is not None:
                    self._release_session_claims(
                        conn,
                        session_id,
                        str(session["actor"]),
                        str(session["repo_path"] or ""),
                        stamp,
                    )
                archived.append(int(session_id))
        for session_id in archived:
            row = self.get_session(session_id)
            if row is None:
                continue
            for binding in bindings_for_session(self.path, session_id):
                delete_binding(
                    self.path,
                    str(binding.get("host", "")),
                    str(binding.get("host_session", "")),
                    str(binding.get("project", "")),
                )
            clear_pointer(self.path, row.actor, row.repo_path, session_id=session_id)
        return len(archived)

    def _release_session_claims(
        self,
        conn: sqlite3.Connection,
        session_id: int,
        actor: str,
        repo_path: str,
        now: float,
    ) -> None:
        """Release leases owned by an archived session's actor in its checkout."""
        rows = conn.execute(
            "SELECT task_id FROM task_claims WHERE actor=? AND repo_path=?",
            (actor, repo_path),
        ).fetchall()
        for row in rows:
            task_id = int(row["task_id"])
            conn.execute("DELETE FROM task_claims WHERE task_id=?", (task_id,))
            self.log(
                actor,
                "task",
                "release",
                f"task #{task_id} released by archived session",
                session_id=session_id,
                now=now,
            )

    def restore_session(
        self, session_id: int, actor: str = "human", now: float | None = None
    ) -> bool:
        """Clear one session's archive stamp; a live row writes no event."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE sessions SET archived_at=0 WHERE id=? AND archived_at<>0",
                (session_id,),
            )
            changed = (cur.rowcount or 0) > 0
            if changed:
                self.log(
                    actor,
                    "session",
                    "restore",
                    f"session S{session_id} restored",
                    session_id=session_id,
                    now=stamp,
                )
        return changed

    def touch_session(
        self,
        session_id: int,
        phase: str | None = None,
        host: str = "",
        now: float | None = None,
        branch: str | None = None,
        plan_id: int | None = None,
        replace_plan: bool = False,
    ) -> Session | None:
        """Refresh one open session's heartbeat and optional attribution."""
        stamp = time.time() if now is None else now
        sets = ["last_seen_at=?"]
        params: list[object] = [stamp]
        if phase is not None:
            sets.append("phase=?")
            params.append(normalize_phase(phase))
        if host:
            sets.append("host=?")
            params.append(str(host)[:64])
        if branch is not None:
            sets.append("branch=?")
            params.append(str(branch).strip())
        if replace_plan:
            sets.append("plan_id=?")
            params.append(plan_id)
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
        base = "SELECT * FROM sessions WHERE ended_at=0 AND archived_at=0 AND repo_path=?"
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
        idle_after: float | None = None,
        repo_path: str = "",
    ) -> list[Session]:
        """Close open sessions whose heartbeat is past their phase's cutoff.

        An explicit *idle_after* overrides the per-phase policy for tests and
        host paths that need one fixed window.
        """
        stamp = time.time() if now is None else now
        sql = "SELECT * FROM sessions WHERE ended_at=0 AND archived_at=0"
        params: list[object] = []
        if repo_path:
            sql += " AND repo_path=?"
            params.append(repo_path)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        closed: list[Session] = []
        for row in rows:
            anchor = float(row["last_seen_at"] or row["started_at"] or 0.0)
            window = idle_after if idle_after is not None else close_after_secs(str(row["phase"]))
            if anchor > stamp - max(window, 0.0):
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
                    now=stamp,
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
        archived: str = "hide",
    ) -> list[Session]:
        """Recent sessions, newest first, with optional actor, plan, and archive filters."""
        check_archive_mode(archived)
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
        if archived == "hide":
            clauses.append("archived_at=0")
        elif archived == "only":
            clauses.append("archived_at>0")
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
        """Most recently ended, unarchived session for a plan or checkout."""
        sql = "SELECT * FROM sessions WHERE ended_at > 0 AND archived_at = 0"
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
