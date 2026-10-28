"""Store methods for claims."""

from __future__ import annotations

import sqlite3
import time

from ..models import (
    Claim,
    Status,
    Task,
)
from .base import (
    ClaimConflict,
    ClaimMissing,
    StoreBase,
)
from .stubs import CLAIM_DEFAULT_TTL


class ClaimsMixin(StoreBase):
    """Claims persistence."""

    @staticmethod
    def _row_to_claim(r: sqlite3.Row) -> Claim:
        """Row to Claim."""
        return Claim(
            task_id=int(r["task_id"]),
            actor=str(r["actor"]),
            started_at=float(r["started_at"]),
            expires_at=float(r["expires_at"]),
            renewed_at=float(r["renewed_at"] or 0),
            note=str(r["note"] or ""),
        )

    @staticmethod
    def _ttl(value: float) -> float:
        ttl = float(value)
        if ttl <= 0:
            raise ValueError("claim ttl must be positive")
        return ttl

    def claim_task(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = CLAIM_DEFAULT_TTL,
        note: str = "",
        force: bool = False,
        now: float | None = None,
    ) -> tuple[Claim, Claim | None]:
        """Take or refresh a task lease; returns the new claim and any previous one."""
        ttl = self._ttl(ttl_seconds)
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute(
                "SELECT id, status, blocked FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
            if task is None:
                raise KeyError(f"task #{task_id} not found")
            if task["status"] == Status.DONE.value:
                raise ValueError("cannot claim a done task")
            if task["blocked"]:
                raise ValueError("cannot claim a blocked task")
            row = conn.execute("SELECT * FROM task_claims WHERE task_id=?", (task_id,)).fetchone()
            previous = self._row_to_claim(row) if row is not None else None
            if (
                previous is not None
                and not previous.expired(stamp)
                and previous.actor != actor
                and not force
            ):
                raise ClaimConflict(previous)
            conn.execute(
                "INSERT INTO task_claims (task_id, actor, note, started_at, expires_at, renewed_at)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(task_id) DO UPDATE SET"
                " actor=excluded.actor, note=excluded.note, started_at=excluded.started_at,"
                " expires_at=excluded.expires_at, renewed_at=excluded.renewed_at",
                (task_id, actor, note, stamp, stamp + ttl, stamp),
            )
        claim = Claim(
            task_id=task_id,
            actor=actor,
            started_at=stamp,
            expires_at=stamp + ttl,
            renewed_at=stamp,
            note=note,
        )
        detail = f"task #{task_id} claimed by {actor} until {int(claim.expires_at)}"
        if previous is not None and previous.actor != actor:
            detail += f" (forced from {previous.actor})"
        self.log(actor, "task", "claim", detail)
        return claim, previous

    def renew_claim(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = CLAIM_DEFAULT_TTL,
        now: float | None = None,
    ) -> Claim:
        """Extend an active lease held by the same actor."""
        ttl = self._ttl(ttl_seconds)
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM task_claims WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                raise ClaimMissing(f"task #{task_id} is not claimed")
            claim = self._row_to_claim(row)
            if claim.expired(stamp):
                raise ClaimConflict(claim, "expired")
            if claim.actor != actor:
                raise ClaimConflict(claim, "held by another actor")
            conn.execute(
                "UPDATE task_claims SET expires_at=?, renewed_at=? WHERE task_id=?",
                (stamp + ttl, stamp, task_id),
            )
        renewed = Claim(
            task_id=task_id,
            actor=actor,
            started_at=claim.started_at,
            expires_at=stamp + ttl,
            renewed_at=stamp,
            note=claim.note,
        )
        self.log(actor, "task", "renew", f"task #{task_id} until {int(renewed.expires_at)}")
        return renewed

    def release_claim(self, task_id: int, actor: str, force: bool = False) -> Claim | None:
        """Release a lease; a different actor needs force."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM task_claims WHERE task_id=?", (task_id,)).fetchone()
            if row is None:
                return None
            claim = self._row_to_claim(row)
            if claim.actor != actor and not force:
                raise ClaimConflict(claim, "held by another actor")
            conn.execute("DELETE FROM task_claims WHERE task_id=?", (task_id,))
        self.log(actor, "task", "release", f"task #{task_id} released")
        return claim

    def get_claim(self, task_id: int) -> Claim | None:
        """Lease on one task, active or expired."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM task_claims WHERE task_id=?", (task_id,)).fetchone()
        return self._row_to_claim(row) if row is not None else None

    def claims_map(self) -> dict[int, Claim]:
        """All leases keyed by task id, for one-query tree rendering."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM task_claims").fetchall()
        return {int(row["task_id"]): self._row_to_claim(row) for row in rows}

    def list_claims(
        self,
        include_expired: bool = False,
        now: float | None = None,
        plan_id: int | None = None,
    ) -> list[dict]:
        """Leases with task and plan context, soonest expiry first."""
        stamp = time.time() if now is None else now
        sql = (
            "SELECT c.*, t.title AS task_title, t.status AS task_status,"
            " t.milestone_id, m.plan_id, p.name AS plan_title"
            " FROM task_claims c"
            " JOIN tasks t ON t.id=c.task_id"
            " JOIN milestones m ON m.id=t.milestone_id"
            " JOIN plans p ON p.id=m.plan_id"
        )
        clauses = []
        params: list[object] = []
        if not include_expired:
            clauses.append("c.expires_at > ?")
            params.append(stamp)
        if plan_id is not None:
            clauses.append("m.plan_id = ?")
            params.append(plan_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY c.expires_at, c.task_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["expired"] = float(item["expires_at"]) <= stamp
            out.append(item)
        return out

    def restore_claim(
        self,
        task_id: int,
        actor: str,
        started_at: float,
        expires_at: float,
        renewed_at: float = 0,
        note: str = "",
    ) -> bool:
        """Import an unexpired lease with its original timestamps."""
        if expires_at <= time.time():
            return False
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO task_claims"
                " (task_id, actor, note, started_at, expires_at, renewed_at)"
                " VALUES (?,?,?,?,?,?)",
                (task_id, actor, note, started_at, expires_at, renewed_at),
            )
        return True

    def next_claimable_task(
        self, plan_id: int | None = None, now: float | None = None
    ) -> Task | None:
        """First unclaimed todo in active plans: doing plans first, then creation order."""
        stamp = time.time() if now is None else now
        sql = (
            "SELECT t.* FROM tasks t"
            " JOIN milestones m ON m.id=t.milestone_id"
            " JOIN plans p ON p.id=m.plan_id"
            " LEFT JOIN task_claims c ON c.task_id=t.id AND c.expires_at > ?"
            " WHERE t.status = 'todo' AND c.task_id IS NULL AND p.status != 'done'"
            " AND t.blocked = 0"
        )
        params: list[object] = [stamp]
        if plan_id is not None:
            sql += " AND p.id = ?"
            params.append(plan_id)
        sql += " ORDER BY CASE WHEN p.status = 'doing' THEN 0 ELSE 1 END, p.id, m.id, t.id LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_task(row) if row is not None else None
