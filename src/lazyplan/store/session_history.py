"""Read-only legacy session history, kept for its original ``S`` ids.

The live registry is :mod:`lazyplan.store.agents`. Old rows stay readable
through ``show``, ``feed``, export, import, and MCP, and maintenance can
archive or restore them, but nothing opens a new one.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Sequence

from ..core.entities import Session
from ..core.policies.maintenance import check_archive_mode
from .base import StoreBase


class SessionHistoryMixin(StoreBase):
    """Query and archive legacy sessions without reviving their lifecycle."""

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
            host=str(r["host"] or ""),
            host_session=str(r["host_session"] or ""),
            auto_closed=bool(r["auto_closed"]),
            archived_at=float(r["archived_at"] or 0),
        )

    def get_session(self, session_id: int) -> Session | None:
        """One historical session by its original id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM session_history WHERE id=?", (session_id,)).fetchone()
        return self._row_to_session(row) if row is not None else None

    def list_sessions(
        self,
        actor: str = "",
        plan_id: int | None = None,
        open_only: bool = False,
        limit: int = 20,
        archived: str = "hide",
    ) -> list[Session]:
        """Recent history rows, newest first, with optional filters."""
        check_archive_mode(archived)
        sql = "SELECT * FROM session_history"
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

    def events_for_session(self, session_id: int, limit: int = 50) -> list[dict]:
        """Newest events tagged with one historical session."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, max(int(limit), 1)),
            ).fetchall()
        return [dict(row) for row in rows]

    def archive_sessions(
        self,
        session_ids: Sequence[int],
        actor: str = "human",
        now: float | None = None,
    ) -> int:
        """Archive ended history rows; open rows are never archived."""
        stamp = time.time() if now is None else now
        archived = 0
        with self._connect() as conn:
            for session_id in session_ids:
                cur = conn.execute(
                    "UPDATE session_history SET archived_at=?"
                    " WHERE id=? AND ended_at>0 AND archived_at=0",
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
                archived += 1
        return archived

    def restore_session(
        self, session_id: int, actor: str = "human", now: float | None = None
    ) -> bool:
        """Clear one history row's archive stamp; a live row writes no event."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE session_history SET archived_at=0 WHERE id=? AND archived_at<>0",
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

    def restore_session_history(self, row: dict, actor: str = "human") -> int | None:
        """Insert one exported history row with its original ``S`` id."""
        try:
            session_id = int(row.get("id", 0) or 0)
        except (TypeError, ValueError):
            return None
        if session_id < 1:
            return None
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT id FROM session_history WHERE id=?", (session_id,)
            ).fetchone()
            if exists is not None:
                return session_id
            conn.execute(
                "INSERT INTO session_history"
                " (id, actor, plan_id, repo_path, branch, started_at, ended_at, summary,"
                " handoff, phase, last_seen_at, host, host_session, auto_closed,"
                " plan_source, archived_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    str(row.get("actor", "") or actor),
                    row.get("plan_id"),
                    str(row.get("repo_path", "") or ""),
                    str(row.get("branch", "") or ""),
                    float(row.get("started_at", 0) or 0),
                    float(row.get("ended_at", 0) or 0),
                    str(row.get("summary", "") or ""),
                    str(row.get("handoff", "") or ""),
                    "working",
                    0.0,
                    str(row.get("host", "") or ""),
                    str(row.get("host_session", "") or ""),
                    int(bool(row.get("auto_closed", False))),
                    "auto",
                    float(row.get("archived_at", 0) or 0),
                ),
            )
        return session_id
