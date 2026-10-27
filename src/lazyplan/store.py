"""SQLite persistence. Stdlib only. Shared by TUI and `lpui` CLI (agent ingress)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .kinds import KIND_ERROR, check_parent_kind, table_for
from .migrate import migrate
from .models import (
    Claim,
    Comment,
    Criterion,
    ForgeLink,
    Milestone,
    Note,
    Plan,
    Status,
    Task,
    VcsLink,
)
from .repo import ensure_plan_dir, resolve_db_path, seed_shared_db, shared_db_path

CLAIM_DEFAULT_TTL = 30 * 60


class ClaimError(RuntimeError):
    """Base error for lease operations."""


class ClaimConflict(ClaimError):
    """A task is held by another actor, or a lease cannot be changed."""

    def __init__(self, claim: Claim, reason: str = "held") -> None:
        self.claim = claim
        self.reason = reason
        super().__init__(
            f"task #{claim.task_id} is claimed by {claim.actor} "
            f"until {int(claim.expires_at)} ({reason})"
        )


class ClaimMissing(ClaimError):
    """No lease exists for the task."""


def _ser(d: dict) -> dict:
    """JSON/agent-safe: Status -> value, omit empty blocked fields."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    if not d.get("blocked"):
        d.pop("blocked", None)
    if not d.get("blocked_reason"):
        d.pop("blocked_reason", None)
    return d


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


def default_actor() -> str:
    """$USER on posix, %USERNAME% on Windows, else human."""
    return (os.environ.get("USER") or os.environ.get("USERNAME") or "human")[:64]


def _actor(explicit: str = "") -> str:
    """Normalize an actor name, defaulting to the login name."""
    if explicit.strip():
        return explicit.strip()[:64]
    return default_actor()


class Store:
    """SQLite persistence shared by the TUI and the lpui CLI."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_db_path(path)
        self._local = threading.local()
        try:
            if Path(self.path).expanduser() == shared_db_path():
                seed_shared_db(self.path)
        except OSError:
            pass
        ensure_plan_dir(self.path)
        with self._connect() as conn:
            migrate(conn)

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

    # -- events (agent feed) -------------------------------------------
    def log(self, actor: str, kind: str, action: str, detail: str = "") -> None:
        """Append an event row."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (ts, actor, kind, action, detail) VALUES (?,?,?,?,?)",
                (time.time(), _actor(actor), kind, action, detail[:500]),
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
        return (mtime, c["plans"], c["milestones"], c["tasks"], mp, ms, mt, me, mc, ml, mr, mf)

    # -- plans ------------------------------------------------------
    def add_plan(
        self,
        name: str,
        description: str = "",
        goal: str = "",
        actor: str = "human",
    ) -> Plan:
        """Insert a plan row and log the event (no template fill; see services)."""
        p = Plan(
            id=0,
            name=name.strip(),
            description=description,
            goal=goal,
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO plans (name, description, status, goal, uid) VALUES (?,?,?,?,?)",
                (p.name, p.description, p.status.value, p.goal, str(uuid.uuid4())),
            )
            p.id = cur.lastrowid or 0
        self.log(actor, "plan", "add", f"P#{p.id} {p.name}")
        return p

    @staticmethod
    def _opt(r: sqlite3.Row, keys: set[str], name: str) -> str:
        """Optional text column, tolerant of legacy tables missing it."""
        return r[name] if name in keys and r[name] else ""

    def _row_to_plan(self, r: sqlite3.Row) -> Plan:
        """Row to Plan (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return Plan(
            id=r["id"],
            name=r["name"],
            description=self._opt(r, keys, "description"),
            status=Status(r["status"]) if "status" in keys else Status.TODO,
            goal=self._opt(r, keys, "goal"),
        )

    def plan_uid(self, pid: int) -> str:
        """Stable uid for one plan."""
        with self._connect() as conn:
            row = conn.execute("SELECT uid FROM plans WHERE id=?", (pid,)).fetchone()
        return str(row["uid"]) if row is not None else ""

    def set_plan_uid(self, pid: int, uid: str) -> bool:
        """Set a plan uid, for import/sync."""
        if not uid.strip():
            raise ValueError("plan uid must not be empty")
        with self._connect() as conn:
            cur = conn.execute("UPDATE plans SET uid=? WHERE id=?", (uid.strip(), pid))
            return (cur.rowcount or 0) > 0

    def get_plan_by_uid(self, uid: str) -> Plan | None:
        """Find a plan by its stable uid."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plans WHERE uid=?", (uid.strip(),)).fetchone()
        return self._row_to_plan(row) if row is not None else None

    def get_plan(self, pid: int) -> Plan | None:
        """Fetch a plan by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM plans WHERE id=?", (pid,)).fetchone()
        return self._row_to_plan(r) if r is not None else None

    def list_plans(self) -> list[Plan]:
        """All plans, newest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM plans ORDER BY id DESC").fetchall()
        return [self._row_to_plan(r) for r in rows]

    def plan_uids_map(self) -> dict[int, str]:
        """Stable plan uid keyed by plan id, in one query."""
        with self._connect() as conn:
            rows = conn.execute("SELECT id, uid FROM plans ORDER BY id").fetchall()
        return {int(row["id"]): str(row["uid"] or "") for row in rows}

    def update_plan(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        actor: str = "human",
    ) -> Plan | None:
        """Patch plan fields and log."""
        p = self.get_plan(pid)
        if p is None:
            return None
        if name is not None:
            if not name.strip():
                raise ValueError("plan name must not be empty")
            p.name = name.strip()
        if description is not None:
            p.description = description
        if goal is not None:
            p.goal = goal
        with self._connect() as conn:
            conn.execute(
                "UPDATE plans SET name=?, description=?, goal=? WHERE id=?",
                (p.name, p.description, p.goal, pid),
            )
        self.log(actor, "plan", "edit", f"P#{pid} {p.name}")
        return p

    # -- milestones -------------------------------------------------------
    def add_milestone(
        self,
        plan_id: int,
        title: str,
        description: str = "",
        actor: str = "human",
    ) -> Milestone:
        """Insert a milestone row and log the event (no template fill; see services)."""
        s = Milestone(
            id=0,
            plan_id=plan_id,
            title=title.strip(),
            description=description,
        )
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise KeyError(f"plan #{plan_id} not found")
            cur = conn.execute(
                "INSERT INTO milestones (plan_id, title, description, status) VALUES (?,?,?,?)",
                (s.plan_id, s.title, s.description, s.status.value),
            )
            s.id = cur.lastrowid or 0
        self.log(actor, "milestone", "add", f"M#{s.id} {s.title}")
        return s

    def _row_to_milestone(self, r: sqlite3.Row) -> Milestone:
        """Row to Milestone (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return Milestone(
            id=r["id"],
            plan_id=r["plan_id"],
            title=r["title"],
            description=self._opt(r, keys, "description"),
            status=Status(r["status"]) if "status" in keys else Status.TODO,
        )

    def get_milestone(self, sid: int) -> Milestone | None:
        """Fetch a milestone by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM milestones WHERE id=?", (sid,)).fetchone()
        return self._row_to_milestone(r) if r is not None else None

    def list_milestones(self, plan_id: int) -> list[Milestone]:
        """Milestones of a plan, in creation order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM milestones WHERE plan_id=? ORDER BY id", (plan_id,)
            ).fetchall()
        return [self._row_to_milestone(r) for r in rows]

    def milestones_map(self) -> dict[int, list[Milestone]]:
        """Every milestone grouped by plan id, in creation order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM milestones ORDER BY id").fetchall()
        out: dict[int, list[Milestone]] = {}
        for row in rows:
            milestone = self._row_to_milestone(row)
            out.setdefault(milestone.plan_id, []).append(milestone)
        return out

    def update_milestone(
        self,
        sid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
    ) -> Milestone | None:
        """Patch milestone fields and log."""
        s = self.get_milestone(sid)
        if s is None:
            return None
        if title is not None:
            if not title.strip():
                raise ValueError("milestone title must not be empty")
            s.title = title.strip()
        if description is not None:
            s.description = description
        with self._connect() as conn:
            conn.execute(
                "UPDATE milestones SET title=?, description=? WHERE id=?",
                (s.title, s.description, sid),
            )
        self.log(actor, "milestone", "edit", f"M#{sid} {s.title}")
        return s

    # -- tasks ---------------------------------------------------------
    def add_task(
        self,
        milestone_id: int,
        title: str,
        description: str = "",
        actor: str = "human",
    ) -> Task:
        """Insert a task row and log the event (no template fill; see services)."""
        t = Task(
            id=0,
            milestone_id=milestone_id,
            title=title.strip(),
            description=description,
        )
        with self._connect() as conn:
            if (
                conn.execute("SELECT 1 FROM milestones WHERE id=?", (milestone_id,)).fetchone()
                is None
            ):
                raise KeyError(f"milestone #{milestone_id} not found")
            cur = conn.execute(
                "INSERT INTO tasks (milestone_id, title, status, description) VALUES (?,?,?,?)",
                (t.milestone_id, t.title, t.status.value, t.description),
            )
            t.id = cur.lastrowid or 0
        self.log(actor, "task", "add", f"T#{t.id} {t.title}")
        return t

    def _row_to_task(self, r: sqlite3.Row) -> Task:
        """Row to Task (tolerates legacy columns on old DBs)."""
        keys = set(r.keys())
        return Task(
            id=r["id"],
            milestone_id=r["milestone_id"],
            title=r["title"],
            status=Status(r["status"]) if "status" in keys else Status.TODO,
            description=self._opt(r, keys, "description"),
            blocked=bool(r["blocked"]) if "blocked" in keys else False,
            blocked_reason=self._opt(r, keys, "blocked_reason"),
        )

    def get_task(self, tid: int) -> Task | None:
        """Fetch a task by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return self._row_to_task(r) if r is not None else None

    def list_tasks(self, milestone_id: int) -> list[Task]:
        """Tasks of a milestone, in creation order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE milestone_id=? ORDER BY id", (milestone_id,)
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def tasks_map(self) -> dict[int, list[Task]]:
        """Every task grouped by milestone id, in creation order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        out: dict[int, list[Task]] = {}
        for row in rows:
            task = self._row_to_task(row)
            out.setdefault(task.milestone_id, []).append(task)
        return out

    # -- task claims (leases) --------------------------------------------
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

    # -- handoff notes (append-only) -------------------------------------
    @staticmethod
    def _row_to_note(r: sqlite3.Row) -> Note:
        """Row to Note."""
        return Note(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
        )

    def add_note(self, parent_kind: str, parent_id: int, text: str, actor: str = "human") -> Note:
        """Append a handoff note and log it."""
        check_parent_kind(parent_kind)
        body = text.strip()
        if not body:
            raise ValueError("note text must not be empty")
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, stamp, body),
            )
            note_id = cur.lastrowid or 0
        self.log(actor, parent_kind, "note", f"{parent_kind} #{parent_id}: {body[:80]}")
        return Note(
            id=note_id,
            parent_kind=parent_kind,
            parent_id=parent_id,
            text=body,
            actor=actor,
            ts=stamp,
        )

    def list_notes(self, parent_kind: str, parent_id: int, limit: int | None = None) -> list[Note]:
        """Notes on one row, oldest first; limit keeps the latest N."""
        check_parent_kind(parent_kind)
        sql = "SELECT * FROM notes WHERE parent_kind=? AND parent_id=? ORDER BY id DESC"
        params: list[object] = [parent_kind, parent_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(int(limit), 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_note(row) for row in reversed(rows)]

    def restore_note(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
    ) -> Note | None:
        """Import a note with its original timestamp."""
        if not text.strip():
            return None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, ts, text.strip()),
            )
            note_id = cur.lastrowid or 0
        return Note(note_id, parent_kind, parent_id, text.strip(), actor, ts)

    # -- issue sources -------------------------------------------------
    def add_issue_link(
        self,
        provider: str,
        external_id: str,
        number: str,
        url: str,
        title: str,
        state: str,
        row_kind: str,
        row_id: int,
        updated_at: float = 0,
    ) -> dict:
        """Record one imported issue source."""
        check_parent_kind(row_kind)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO issue_links"
                " (provider, external_id, number, url, title, state, row_kind, row_id, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (provider, external_id, number, url, title, state, row_kind, row_id, updated_at),
            )
            link_id = cur.lastrowid or 0
        return {
            "id": link_id,
            "provider": provider,
            "external_id": external_id,
            "number": number,
            "url": url,
            "title": title,
            "state": state,
            "row_kind": row_kind,
            "row_id": row_id,
            "updated_at": updated_at,
        }

    def get_issue_link(self, provider: str, external_id: str) -> dict | None:
        """Find a source link by provider and external id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM issue_links WHERE provider=? AND external_id=?",
                (provider, external_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_issue_links(self, row_kind: str, row_id: int) -> list[dict]:
        """Issue sources attached to one row."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM issue_links WHERE row_kind=? AND row_id=? ORDER BY id",
                (row_kind, row_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def issue_links_map(self) -> dict[tuple[str, int], list[dict]]:
        """Every issue source grouped by (row_kind, row_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM issue_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[dict]] = {}
        for row in rows:
            item = dict(row)
            out.setdefault((str(item["row_kind"]), int(item["row_id"])), []).append(item)
        return out

    def update_issue_link(
        self, provider: str, external_id: str, title: str, url: str, state: str, updated_at: float
    ) -> bool:
        """Refresh cached source metadata without touching the row."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE issue_links SET title=?, url=?, state=?, updated_at=?"
                " WHERE provider=? AND external_id=?",
                (title, url, state, updated_at, provider, external_id),
            )
            return (cur.rowcount or 0) > 0

    # -- review comments ------------------------------------------------
    @staticmethod
    def _row_to_comment(r: sqlite3.Row) -> Comment:
        """Row to Comment."""
        return Comment(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
            resolved=bool(r["resolved"]),
        )

    def add_comment(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Comment:
        """Append a review comment and log it."""
        check_parent_kind(parent_kind)
        body = text.strip()
        if not body:
            raise ValueError("comment text must not be empty")
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, stamp, body),
            )
            comment_id = cur.lastrowid or 0
        self.log(actor, parent_kind, "comment", f"{parent_kind} #{parent_id}: {body[:80]}")
        return Comment(comment_id, parent_kind, parent_id, body, actor, stamp, False)

    def list_comments(
        self, parent_kind: str, parent_id: int, mentions: str | None = None
    ) -> list[Comment]:
        """Comments on one row, oldest first; optionally only @name mentions."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM comments WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        items = [self._row_to_comment(row) for row in rows]
        if mentions:
            needle = f"@{mentions.lstrip('@').lower()}"
            items = [item for item in items if needle in item.text.lower()]
        return items

    def resolve_comment(
        self, cid: int, resolved: bool = True, actor: str = "human"
    ) -> Comment | None:
        """Set or clear a comment's resolved flag."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM comments WHERE id=?", (cid,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE comments SET resolved=? WHERE id=?", (1 if resolved else 0, cid))
        self.log(actor, "comment", "resolve" if resolved else "unresolve", f"comment #{cid}")
        comment = self._row_to_comment(row)
        return Comment(
            comment.id,
            comment.parent_kind,
            comment.parent_id,
            comment.text,
            comment.actor,
            comment.ts,
            resolved,
        )

    def restore_comment(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
        resolved: bool,
    ) -> Comment | None:
        """Import a comment with its timestamp and resolution state."""
        if not text.strip():
            return None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text, resolved)"
                " VALUES (?,?,?,?,?,?)",
                (parent_kind, parent_id, actor, ts, text.strip(), 1 if resolved else 0),
            )
            comment_id = cur.lastrowid or 0
        return Comment(comment_id, parent_kind, parent_id, text.strip(), actor, ts, resolved)

    def notes_map(self) -> dict[tuple[str, int], list[str]]:
        """All note text grouped by parent, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute("SELECT parent_kind, parent_id, text FROM notes").fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["parent_kind"]), int(row["parent_id"])), []).append(
                str(row["text"])
            )
        return out

    def comments_map(self) -> dict[tuple[str, int], list[str]]:
        """All comment text grouped by parent, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute("SELECT parent_kind, parent_id, text FROM comments").fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["parent_kind"]), int(row["parent_id"])), []).append(
                str(row["text"])
            )
        return out

    def notes_full_map(self) -> dict[tuple[str, int], list[Note]]:
        """Every note grouped by parent, oldest first, with full metadata."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Note]] = {}
        for row in rows:
            note = self._row_to_note(row)
            out.setdefault((note.parent_kind, note.parent_id), []).append(note)
        return out

    def comments_full_map(self) -> dict[tuple[str, int], list[Comment]]:
        """Every comment grouped by parent, oldest first, with full metadata."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM comments ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Comment]] = {}
        for row in rows:
            comment = self._row_to_comment(row)
            out.setdefault((comment.parent_kind, comment.parent_id), []).append(comment)
        return out

    def issues_map(self) -> dict[tuple[str, int], list[str]]:
        """Issue source text grouped by row, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT row_kind, row_id, provider, number, title, url FROM issue_links"
            ).fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["row_kind"]), int(row["row_id"])), []).append(
                " ".join(str(row[key]) for key in ("provider", "number", "title", "url"))
            )
        return out

    def update_task(
        self,
        tid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
    ) -> Task | None:
        """Patch task fields and log."""
        t = self.get_task(tid)
        if t is None:
            return None
        if title is not None:
            if not title.strip():
                raise ValueError("task title must not be empty")
            t.title = title.strip()
        if description is not None:
            t.description = description
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET title=?, description=? WHERE id=?",
                (t.title, t.description, tid),
            )
        self.log(actor, "task", "edit", f"T#{tid} {t.title}")
        return t

    def set_blocked(
        self, tid: int, blocked: bool, reason: str = "", actor: str = "human"
    ) -> Task | None:
        """Set or clear the blocked flag on a task."""
        if blocked and not reason.strip():
            raise ValueError("blocking a task needs a reason")
        t = self.get_task(tid)
        if t is None:
            return None
        text = reason.strip() if blocked else ""
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET blocked=?, blocked_reason=? WHERE id=?",
                (1 if blocked else 0, text, tid),
            )
        t.blocked = blocked
        t.blocked_reason = text
        self.log(actor, "task", "block" if blocked else "unblock", f"T#{tid} {text}".strip())
        return t

    def gate_state(self, task_id: int) -> dict:
        """Cached PR/check state for a task without network access."""
        links = self.effective_forge_links("task", task_id)
        if not links:
            return {"prs": 0, "checks": "none", "state": "missing"}
        values = [str(link.checks or "none") for link in links]
        if any(value == "fail" for value in values):
            checks = "fail"
        elif any(value == "pending" for value in values):
            checks = "pending"
        elif all(value in {"pass", "neutral", "skipped"} for value in values):
            checks = "pass"
        else:
            checks = "none"
        return {
            "prs": len(links),
            "checks": checks,
            "state": "pass" if checks == "pass" else checks,
        }

    def branch_owners(
        self,
        repo_path: str,
        branch: str,
        remote: str = "",
        exclude_task: int = 0,
    ) -> list[Task]:
        """Open tasks that already record this branch in the checkout or a shared remote."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT t.* FROM entity_repos r"
                " JOIN tasks t ON t.id=r.parent_id"
                " WHERE r.parent_kind='task' AND r.branch=?"
                " AND t.status != 'done' AND t.id != ?"
                " AND (r.repo_path=? OR (? != '' AND r.repo_remote=?))"
                " ORDER BY t.id",
                (branch, exclude_task, repo_path, remote, remote),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def delete(self, kind: str, obj_id: int, actor: str = "human") -> bool:
        """Delete a row and its subtree (criteria/links/repos purged; FK cascades rest)."""
        table = table_for(kind)
        with self._connect() as conn:
            if kind == "plan":
                sids = [
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM milestones WHERE plan_id=?", (obj_id,)
                    ).fetchall()
                ]
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='plan' AND parent_id=?", (obj_id,)
                )
                conn.execute(
                    "DELETE FROM vcs_links WHERE parent_kind='plan' AND parent_id=?",
                    (obj_id,),
                )
                conn.execute(
                    "DELETE FROM forge_links WHERE parent_kind='plan' AND parent_id=?",
                    (obj_id,),
                )
                self._delete_entity_repos(conn, "plan", obj_id)
                self._delete_notes(conn, "plan", obj_id)
                self._delete_comments(conn, "plan", obj_id)
                for sid in sids:
                    self._delete_milestone_criteria(conn, sid)
                    self._delete_milestone_links(conn, sid)
                    self._delete_milestone_repos(conn, sid)
                    self._delete_milestone_forge_links(conn, sid)
                    self._delete_milestone_notes(conn, sid)
                    self._delete_milestone_comments(conn, sid)
            elif kind == "milestone":
                self._delete_milestone_criteria(conn, obj_id)
                self._delete_milestone_links(conn, obj_id)
                self._delete_milestone_repos(conn, obj_id)
                self._delete_milestone_forge_links(conn, obj_id)
                self._delete_milestone_notes(conn, obj_id)
                self._delete_milestone_comments(conn, obj_id)
            else:
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
                conn.execute(
                    "DELETE FROM vcs_links WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
                conn.execute(
                    "DELETE FROM forge_links WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
                self._delete_entity_repos(conn, "task", obj_id)
                self._delete_notes(conn, "task", obj_id)
                self._delete_comments(conn, "task", obj_id)
            cur = conn.execute(f"DELETE FROM {table} WHERE id=?", (obj_id,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, kind, "delete", f"{kind} #{obj_id}")
        return ok

    @staticmethod
    def _delete_milestone_criteria(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove criteria under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        conn.execute(
            "DELETE FROM criteria WHERE parent_kind='milestone' AND parent_id=?", (milestone_id,)
        )
        for tid in tids:
            conn.execute("DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (tid,))

    @staticmethod
    def _delete_milestone_links(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove VCS links under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        conn.execute(
            "DELETE FROM vcs_links WHERE parent_kind='milestone' AND parent_id=?", (milestone_id,)
        )
        for tid in tids:
            conn.execute("DELETE FROM vcs_links WHERE parent_kind='task' AND parent_id=?", (tid,))

    @staticmethod
    def _delete_milestone_repos(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove repo links under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        Store._delete_entity_repos(conn, "milestone", milestone_id)
        for tid in tids:
            Store._delete_entity_repos(conn, "task", tid)

    @staticmethod
    def _delete_notes(conn: sqlite3.Connection, parent_kind: str, parent_id: int) -> None:
        """Remove notes on one row."""
        conn.execute(
            "DELETE FROM notes WHERE parent_kind=? AND parent_id=?", (parent_kind, parent_id)
        )

    @staticmethod
    def _delete_comments(conn: sqlite3.Connection, parent_kind: str, parent_id: int) -> None:
        """Remove comments on one row."""
        conn.execute(
            "DELETE FROM comments WHERE parent_kind=? AND parent_id=?", (parent_kind, parent_id)
        )

    @staticmethod
    def _delete_milestone_comments(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove comments under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        Store._delete_comments(conn, "milestone", milestone_id)
        for tid in tids:
            Store._delete_comments(conn, "task", tid)

    @staticmethod
    def _delete_milestone_notes(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove notes under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        Store._delete_notes(conn, "milestone", milestone_id)
        for tid in tids:
            Store._delete_notes(conn, "task", tid)

    @staticmethod
    def _delete_milestone_forge_links(conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove forge links under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        conn.execute(
            "DELETE FROM forge_links WHERE parent_kind='milestone' AND parent_id=?",
            (milestone_id,),
        )
        for tid in tids:
            conn.execute("DELETE FROM forge_links WHERE parent_kind='task' AND parent_id=?", (tid,))

    # -- criteria (acceptance checklists, advisory only) -----------------
    def _parent_exists(self, parent_kind: str, parent_id: int) -> bool:
        """True when the criteria parent row exists."""
        if parent_kind == "plan":
            return self.get_plan(parent_id) is not None
        if parent_kind == "milestone":
            return self.get_milestone(parent_id) is not None
        return self.get_task(parent_id) is not None

    def add_criteria(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Criterion:
        """Add an acceptance checklist item and log."""
        c = Criterion(id=0, parent_kind=parent_kind, parent_id=parent_id, text=text.strip())
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO criteria (parent_kind, parent_id, text, done) VALUES (?,?,?,0)",
                (c.parent_kind, c.parent_id, c.text),
            )
            c.id = cur.lastrowid or 0
        self.log(actor, "criteria", "add", f"{parent_kind} #{parent_id}: {c.text[:80]}")
        return c

    @staticmethod
    def _row_to_criterion(r: sqlite3.Row) -> Criterion:
        """Row to Criterion."""
        return Criterion(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            done=bool(r["done"]),
        )

    def get_criterion(self, cid: int) -> Criterion | None:
        """Fetch one checklist item by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM criteria WHERE id=?", (cid,)).fetchone()
        return self._row_to_criterion(r) if r is not None else None

    def relate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        """Record that a task proves a criterion."""
        if self.get_criterion(criterion_id) is None:
            raise KeyError(f"criterion #{criterion_id} not found")
        if self.get_task(task_id) is None:
            raise KeyError(f"task #{task_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO criterion_links (criterion_id, task_id) VALUES (?,?)",
                (criterion_id, task_id),
            )
            inserted = (cur.rowcount or 0) > 0
        if not inserted:
            raise ValueError(f"criterion #{criterion_id} is already linked to task #{task_id}")
        self.log(
            actor,
            "criterion",
            "relate",
            f"criterion #{criterion_id} <- task #{task_id}",
        )
        return True

    def unrelate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        """Remove a criterion-task proof relation."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM criterion_links WHERE criterion_id=? AND task_id=?",
                (criterion_id, task_id),
            )
            removed = (cur.rowcount or 0) > 0
        if removed:
            self.log(
                actor,
                "criterion",
                "unrelate",
                f"criterion #{criterion_id} -/-> task #{task_id}",
            )
        return removed

    def criterion_tasks(self, criterion_id: int) -> list[Task]:
        """Tasks that prove one criterion, in task id order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.* FROM tasks t"
                " JOIN criterion_links l ON l.task_id=t.id"
                " WHERE l.criterion_id=? ORDER BY t.id",
                (criterion_id,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def task_criteria(self, task_id: int) -> list[Criterion]:
        """Criteria proved by one task, in criterion id order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.* FROM criteria c"
                " JOIN criterion_links l ON l.criterion_id=c.id"
                " WHERE l.task_id=? ORDER BY c.id",
                (task_id,),
            ).fetchall()
        return [self._row_to_criterion(r) for r in rows]

    def all_criterion_links(self) -> list[dict]:
        """Every criterion-task relation, for export."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT criterion_id, task_id FROM criterion_links ORDER BY criterion_id, task_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]:
        """Checklist items of a plan, milestone, or task."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criteria WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [self._row_to_criterion(r) for r in rows]

    def criteria_map(self) -> dict[tuple[str, int], list[Criterion]]:
        """Every checklist item grouped by (parent_kind, parent_id), in id order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM criteria ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Criterion]] = {}
        for row in rows:
            criterion = self._row_to_criterion(row)
            out.setdefault((criterion.parent_kind, criterion.parent_id), []).append(criterion)
        return out

    def open_task_criteria_ids(self) -> set[int]:
        """Task ids that still have at least one open criterion."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT parent_id FROM criteria"
                " WHERE parent_kind='task' AND done=0 ORDER BY parent_id"
            ).fetchall()
        return {int(row["parent_id"]) for row in rows}

    def set_criteria(self, cid: int, done: bool, actor: str = "human") -> Criterion | None:
        """Tick or untick a checklist item and log."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM criteria WHERE id=?", (cid,)).fetchone()
            if r is None:
                return None
            conn.execute("UPDATE criteria SET done=? WHERE id=?", (1 if done else 0, cid))
        self.log(actor, "criteria", "check" if done else "uncheck", f"criteria #{cid}")
        return Criterion(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            text=r["text"],
            done=done,
        )

    def delete_criteria(self, cid: int, actor: str = "human") -> bool:
        """Remove a checklist item and log."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM criteria WHERE id=?", (cid,))
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "criteria", "delete", f"criteria #{cid}")
        return ok

    def criteria_progress(self, parent_kind: str, parent_id: int) -> tuple[int, int]:
        """Return (done, total) for a parent."""
        items = self.list_criteria(parent_kind, parent_id)
        return sum(1 for c in items if c.done), len(items)

    def open_criteria(self, kind: str, obj_id: int) -> list[Criterion]:
        """Not-done checklist items."""
        return [c for c in self.list_criteria(kind, obj_id) if not c.done]

    # -- VCS links (commits attached to P/S/T) ------------------------------
    @staticmethod
    def _row_to_link(r: sqlite3.Row) -> VcsLink:
        """Row to VcsLink."""
        return VcsLink(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            sha=r["sha"],
            subject=r["subject"] or "",
            author=r["author"] or "",
            timestamp=int(r["timestamp"] or 0),
            repo_root=r["repo_root"] or "",
            files=_files_tuple(r["files"] or "") if "files" in r.keys() else (),
            stale=bool(r["stale"]) if "stale" in r.keys() else False,
            checked_at=int(r["checked_at"] or 0) if "checked_at" in r.keys() else 0,
        )

    def link_commit(
        self,
        parent_kind: str,
        parent_id: int,
        sha: str,
        subject: str = "",
        author: str = "",
        timestamp: int = 0,
        repo_root: str = "",
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink:
        """Attach a commit to a plan, milestone, or task (idempotent on re-link)."""
        link = VcsLink(
            id=0,
            parent_kind=parent_kind,
            parent_id=parent_id,
            sha=sha,
            subject=subject,
            author=author,
            timestamp=timestamp,
            repo_root=repo_root,
            files=files,
        )
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        files_json = _files_json(files)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO vcs_links"
                " (parent_kind, parent_id, sha, subject, author, timestamp, repo_root, files)"
                " VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(parent_kind, parent_id, sha) DO UPDATE SET"
                " subject=CASE WHEN excluded.subject <> '' THEN excluded.subject ELSE subject END,"
                " author=CASE WHEN excluded.author <> '' THEN excluded.author ELSE author END,"
                " timestamp=CASE WHEN excluded.timestamp > 0 THEN excluded.timestamp ELSE timestamp END,"
                " repo_root=CASE WHEN excluded.repo_root <> '' THEN excluded.repo_root ELSE repo_root END,"
                " files=CASE WHEN excluded.files <> '[]' THEN excluded.files ELSE files END",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.sha,
                    link.subject,
                    link.author,
                    link.timestamp,
                    link.repo_root,
                    files_json,
                ),
            )
            r = conn.execute(
                "SELECT * FROM vcs_links WHERE parent_kind=? AND parent_id=? AND sha=?",
                (link.parent_kind, link.parent_id, link.sha),
            ).fetchone()
            assert r is not None
            link = self._row_to_link(r)
        self.log(actor, "vcs", "link", f"{parent_kind} #{parent_id}: {link.sha[:12]}")
        return link

    def update_link(
        self,
        link_id: int,
        *,
        subject: str,
        author: str,
        timestamp: int,
        repo_root: str,
        stale: bool,
        checked_at: int,
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink | None:
        """Refresh one link's cached metadata, files, and stale flag; None when gone."""
        files_json = _files_json(files)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE vcs_links SET subject=?, author=?, timestamp=?, repo_root=?,"
                " files=CASE WHEN ? <> '[]' THEN ? ELSE files END,"
                " stale=?, checked_at=? WHERE id=?",
                (
                    subject,
                    author,
                    timestamp,
                    repo_root,
                    files_json,
                    files_json,
                    1 if stale else 0,
                    checked_at,
                    link_id,
                ),
            )
            if (cur.rowcount or 0) == 0:
                return None
            r = conn.execute("SELECT * FROM vcs_links WHERE id=?", (link_id,)).fetchone()
        if r is None:
            return None
        link = self._row_to_link(r)
        state = "stale" if link.stale else "ok"
        self.log(actor, "vcs", "refresh", f"link #{link_id}: {state}")
        return link

    def unlink_commit(
        self, parent_kind: str, parent_id: int, sha: str, actor: str = "human"
    ) -> bool:
        """Detach a commit; True when a row was removed."""
        check_parent_kind(parent_kind)
        norm = sha.strip().lower()
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM vcs_links WHERE parent_kind=? AND parent_id=? AND sha=?",
                (parent_kind, parent_id, norm),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "vcs", "unlink", f"{parent_kind} #{parent_id}: {norm[:12]}")
        return ok

    def list_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        """Commits attached to a plan, milestone, or task, oldest first."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vcs_links WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [self._row_to_link(r) for r in rows]

    def links_for_sha(self, sha: str) -> list[VcsLink]:
        """Every link pointing at one commit, oldest first."""
        norm = sha.strip().lower()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM vcs_links WHERE sha=? ORDER BY id",
                (norm,),
            ).fetchall()
        return [self._row_to_link(r) for r in rows]

    # -- forge links (pull requests and issues) ---------------------------
    @staticmethod
    def _row_to_forge_link(r: sqlite3.Row) -> ForgeLink:
        """Row to ForgeLink."""
        return ForgeLink(
            id=r["id"],
            parent_kind=r["parent_kind"],
            parent_id=r["parent_id"],
            provider=r["provider"] or "github",
            kind=r["kind"] or "pull",
            number=int(r["number"] or 0),
            url=r["url"] or "",
            title=r["title"] or "",
            state=r["state"] or "",
            checks=r["checks"] or "",
            reviews=r["reviews"] or "",
            author=r["author"] or "",
            base_ref=r["base_ref"] or "",
            head_ref=r["head_ref"] or "",
            merged_at=r["merged_at"] or "",
            merge_commit_sha=r["merge_commit_sha"] or "",
            updated_at=int(r["updated_at"] or 0),
            stale=bool(r["stale"]) if "stale" in r.keys() else False,
            payload=r["payload"] or "",
        )

    def link_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        url: str = "",
        title: str = "",
        state: str = "",
        checks: str = "",
        reviews: str = "",
        author: str = "",
        base_ref: str = "",
        head_ref: str = "",
        merged_at: str = "",
        merge_commit_sha: str = "",
        updated_at: int = 0,
        stale: bool = False,
        payload: str = "",
        actor: str = "human",
    ) -> ForgeLink:
        """Attach a pull request/issue to a row, refreshing its cached fields."""
        check_parent_kind(parent_kind)
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        link = ForgeLink(
            id=0,
            parent_kind=parent_kind,
            parent_id=parent_id,
            provider=provider,
            kind=kind,
            number=int(number),
            url=url,
            title=title,
            state=state,
            checks=checks,
            reviews=reviews,
            author=author,
            base_ref=base_ref,
            head_ref=head_ref,
            merged_at=merged_at,
            merge_commit_sha=merge_commit_sha,
            updated_at=updated_at,
            stale=stale,
            payload=payload,
        )
        existing_state = ""
        existing_checks = ""
        existing_reviews = ""
        existing_merged = ""
        existed = False
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT state, checks, reviews, merged_at FROM forge_links"
                " WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                ),
            ).fetchone()
            if existing is not None:
                existed = True
                existing_state = str(existing["state"] or "")
                existing_checks = str(existing["checks"] or "")
                existing_reviews = str(existing["reviews"] or "")
                existing_merged = str(existing["merged_at"] or "")
            conn.execute(
                "INSERT INTO forge_links"
                " (parent_kind, parent_id, provider, kind, number, url, title, state,"
                " checks, reviews, author, base_ref, head_ref, merged_at,"
                " merge_commit_sha, updated_at, stale, payload)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(parent_kind, parent_id, provider, kind, number)"
                " DO UPDATE SET url=excluded.url, title=excluded.title,"
                " state=excluded.state, checks=excluded.checks,"
                " reviews=excluded.reviews, author=excluded.author,"
                " base_ref=excluded.base_ref, head_ref=excluded.head_ref,"
                " merged_at=excluded.merged_at,"
                " merge_commit_sha=excluded.merge_commit_sha,"
                " updated_at=excluded.updated_at, stale=excluded.stale,"
                " payload=excluded.payload",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                    link.url,
                    link.title,
                    link.state,
                    link.checks,
                    link.reviews,
                    link.author,
                    link.base_ref,
                    link.head_ref,
                    link.merged_at,
                    link.merge_commit_sha,
                    link.updated_at,
                    1 if link.stale else 0,
                    link.payload,
                ),
            )
            r = conn.execute(
                "SELECT * FROM forge_links WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.provider,
                    link.kind,
                    link.number,
                ),
            ).fetchone()
            assert r is not None
            link = self._row_to_forge_link(r)
        if not existed:
            self.log(
                actor,
                "forge",
                "link",
                f"{link.kind} #{link.number} -> {parent_kind} #{parent_id}",
            )
        elif (
            existing_state != link.state
            or existing_checks != link.checks
            or existing_reviews != link.reviews
            or existing_merged != link.merged_at
        ):
            self.log(
                actor,
                "forge",
                "state",
                f"{link.kind} #{link.number}: {existing_state or 'unknown'} ->"
                f" {link.state or 'unknown'}",
            )
        return link

    def unlink_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        actor: str = "human",
    ) -> bool:
        """Detach one forge link; True when a row was removed."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM forge_links WHERE parent_kind=? AND parent_id=?"
                " AND provider=? AND kind=? AND number=?",
                (parent_kind, parent_id, provider, kind, int(number)),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "forge", "unlink", f"{kind} #{number} -> {parent_kind} #{parent_id}")
        return ok

    def list_forge_links(
        self,
        parent_kind: str,
        parent_id: int,
        kind: str = "",
    ) -> list[ForgeLink]:
        """Forge links on one row, oldest first (optionally one kind)."""
        check_parent_kind(parent_kind)
        sql = "SELECT * FROM forge_links WHERE parent_kind=? AND parent_id=?"
        params: list[object] = [parent_kind, parent_id]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_forge_link(r) for r in rows]

    def effective_forge_links(
        self,
        parent_kind: str,
        parent_id: int,
        kind: str = "",
    ) -> list[ForgeLink]:
        """Direct forge links plus descendant links, deduped by identity."""
        check_parent_kind(parent_kind)
        links = list(self.list_forge_links(parent_kind, parent_id, kind))
        if parent_kind == "milestone":
            for task in self.list_tasks(parent_id):
                links.extend(self.list_forge_links("task", task.id, kind))
        elif parent_kind == "plan":
            for milestone in self.list_milestones(parent_id):
                links.extend(self.list_forge_links("milestone", milestone.id, kind))
                for task in self.list_tasks(milestone.id):
                    links.extend(self.list_forge_links("task", task.id, kind))
        seen: set[tuple[str, str, int]] = set()
        out: list[ForgeLink] = []
        for link in links:
            key = (link.provider, link.kind, link.number)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def forge_links_map(self) -> dict[tuple[str, int], list[ForgeLink]]:
        """Every forge link grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM forge_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[ForgeLink]] = {}
        for row in rows:
            link = self._row_to_forge_link(row)
            out.setdefault((link.parent_kind, link.parent_id), []).append(link)
        return out

    def vcs_links_map(self) -> dict[tuple[str, int], list[VcsLink]]:
        """Every commit link grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM vcs_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[VcsLink]] = {}
        for row in rows:
            link = self._row_to_link(row)
            out.setdefault((link.parent_kind, link.parent_id), []).append(link)
        return out

    def cache_get(self, key: str) -> dict | None:
        """Cached HTTP entry by key, or None."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM forge_cache WHERE key=?", (key,)).fetchone()
        return dict(r) if r is not None else None

    def cache_put(self, key: str, etag: str, fetched_at: int, payload: str) -> None:
        """Store or replace one cached HTTP response."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO forge_cache (key, etag, fetched_at, payload)"
                " VALUES (?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET etag=excluded.etag,"
                " fetched_at=excluded.fetched_at, payload=excluded.payload",
                (key, etag, int(fetched_at), payload),
            )

    def effective_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        """Direct links plus descendants, deduped by SHA and checkout.

        Plans include their milestones and tasks; milestones include their
        tasks. Direct links stay first, then child links in creation order.
        """
        check_parent_kind(parent_kind)
        links = list(self.list_links(parent_kind, parent_id))
        if parent_kind == "milestone":
            for task in self.list_tasks(parent_id):
                links.extend(self.list_links("task", task.id))
        elif parent_kind == "plan":
            for milestone in self.list_milestones(parent_id):
                links.extend(self.list_links("milestone", milestone.id))
                for task in self.list_tasks(milestone.id):
                    links.extend(self.list_links("task", task.id))
        seen: set[tuple[str, str]] = set()
        out: list[VcsLink] = []
        for link in links:
            key = (link.sha, link.repo_root)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    # -- linked repos (0..n checkouts per plan/milestone/task) ------------
    @staticmethod
    def _norm_repo_path(path: str | Path) -> str:
        """Absolute normalized repo path (no existence requirement)."""
        p = Path(str(path)).expanduser()
        try:
            return str(p.resolve())
        except OSError:
            return str(p.absolute())

    def add_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str = "",
        branch: str = "",
        base_sha: str = "",
        actor: str = "human",
    ) -> dict:
        """Link a repo checkout to a row (idempotent on re-link)."""
        check_parent_kind(parent_kind)
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        norm_path = self._norm_repo_path(repo_path)
        if not norm_path.strip():
            raise ValueError("repo path must not be empty")
        remote = (repo_remote or "").strip()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO entity_repos"
                " (parent_kind, parent_id, repo_path, repo_remote, branch, base_sha)"
                " VALUES (?,?,?,?,?,?)",
                (parent_kind, parent_id, norm_path, remote, branch.strip(), base_sha.strip()),
            )
            if branch or base_sha:
                conn.execute(
                    "UPDATE entity_repos SET branch=?, base_sha=?"
                    " WHERE parent_kind=? AND parent_id=? AND repo_path=? AND repo_remote=?",
                    (
                        branch.strip(),
                        base_sha.strip(),
                        parent_kind,
                        parent_id,
                        norm_path,
                        remote,
                    ),
                )
            r = conn.execute(
                "SELECT * FROM entity_repos WHERE parent_kind=? AND parent_id=?"
                " AND repo_path=? AND repo_remote=?",
                (parent_kind, parent_id, norm_path, remote),
            ).fetchone()
            assert r is not None
            row = dict(r)
        self.log(actor, "repo", "link", f"{parent_kind} #{parent_id}: {norm_path}")
        return row

    def remove_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str | None = None,
        actor: str = "human",
    ) -> bool:
        """Unlink a repo; without remote, removes all remotes for the path."""
        check_parent_kind(parent_kind)
        norm_path = self._norm_repo_path(repo_path)
        with self._connect() as conn:
            if repo_remote is None:
                cur = conn.execute(
                    "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=? AND repo_path=?",
                    (parent_kind, parent_id, norm_path),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=?"
                    " AND repo_path=? AND repo_remote=?",
                    (parent_kind, parent_id, norm_path, (repo_remote or "").strip()),
                )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "repo", "unlink", f"{parent_kind} #{parent_id}: {norm_path}")
        return ok

    def list_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        """Explicit repo links on one row, oldest first."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entity_repos WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def effective_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        """Effective repos: explicit links, else inherited from parent plan."""
        check_parent_kind(parent_kind)
        explicit = self.list_repos(parent_kind, parent_id)
        if explicit:
            return explicit
        if parent_kind == "task":
            t = self.get_task(parent_id)
            if t is not None:
                return self.effective_repos("milestone", t.milestone_id)
        elif parent_kind == "milestone":
            s = self.get_milestone(parent_id)
            if s is not None:
                return self.list_repos("plan", s.plan_id)
        return []

    def repos_map(self) -> dict[tuple[str, int], list[dict]]:
        """Every linked repo grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT id, parent_kind, parent_id, repo_path, repo_remote, branch, base_sha"
                    " FROM entity_repos ORDER BY id"
                ).fetchall()
            except Exception:
                return {}
        out: dict[tuple[str, int], list[dict]] = {}
        for r in rows:
            out.setdefault((r["parent_kind"], r["parent_id"]), []).append(dict(r))
        return out

    @staticmethod
    def _delete_entity_repos(conn: sqlite3.Connection, kind: str, obj_id: int) -> None:
        """Remove repo links on one row (callers handle subtree fan-out)."""
        try:
            conn.execute(
                "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=?", (kind, obj_id)
            )
        except Exception:
            pass

    def get_parent(self, kind: str, obj_id: int) -> Plan | Milestone | Task | None:
        """Fetch any row by kind (criteria parent lookup)."""
        if kind == "plan":
            return self.get_plan(obj_id)
        if kind == "milestone":
            return self.get_milestone(obj_id)
        if kind == "task":
            return self.get_task(obj_id)
        raise ValueError(KIND_ERROR)

    # -- export / import (portability) -----------------------------------
    def _task_view(self, t: Task) -> dict:
        """Task fields plus any active or expired claim."""
        data = _ser(vars(t))
        claim = self.get_claim(t.id)
        if claim is not None:
            data["claim"] = vars(claim)
        notes = self.list_notes("task", t.id)
        if notes:
            data["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("task", t.id)
        if comments:
            data["comments"] = [vars(c) for c in comments]
        gate = self.gate_state(t.id)
        if gate["prs"]:
            data["gate"] = gate
        issue_refs = self.list_issue_links("task", t.id)
        if issue_refs:
            data["issues"] = issue_refs
        return data

    def _task_show(self, t: Task) -> dict:
        """Task show payload with direct links and inherited repos."""
        return {
            "task": self._task_view(t),
            "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
            "links": [vars(c) for c in self.list_links("task", t.id)],
            "effective_links": [vars(c) for c in self.effective_links("task", t.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("task", t.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("task", t.id)],
            "repos": self.list_repos("task", t.id),
            "effective_repos": self.effective_repos("task", t.id),
        }

    def _milestone_show(self, s: Milestone) -> dict:
        """Milestone show payload with task summaries."""
        payload = {
            "milestone": _ser(vars(s)),
            "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
            "links": [vars(c) for c in self.list_links("milestone", s.id)],
            "effective_links": [vars(c) for c in self.effective_links("milestone", s.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("milestone", s.id)],
            "effective_forge_links": [
                vars(c) for c in self.effective_forge_links("milestone", s.id)
            ],
            "repos": self.list_repos("milestone", s.id),
            "effective_repos": self.effective_repos("milestone", s.id),
            "tasks": [
                {
                    "task": self._task_view(t),
                    "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                }
                for t in self.list_tasks(s.id)
            ],
        }
        notes = self.list_notes("milestone", s.id)
        if notes:
            payload["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("milestone", s.id)
        if comments:
            payload["comments"] = [vars(c) for c in comments]
        issue_refs = self.list_issue_links("milestone", s.id)
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def _plan_show(self, p: Plan) -> dict:
        """Plan show payload with milestone summaries."""
        payload = {
            "plan": _ser(vars(p)),
            "criteria": [vars(c) for c in self.list_criteria("plan", p.id)],
            "links": [vars(c) for c in self.list_links("plan", p.id)],
            "effective_links": [vars(c) for c in self.effective_links("plan", p.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("plan", p.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("plan", p.id)],
            "repos": self.list_repos("plan", p.id),
            "effective_repos": self.effective_repos("plan", p.id),
            "milestones": [
                {
                    "milestone": _ser(vars(s)),
                    "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
                    "repos": self.list_repos("milestone", s.id),
                    "effective_repos": self.effective_repos("milestone", s.id),
                    "tasks": [self._task_view(t) for t in self.list_tasks(s.id)],
                }
                for s in self.list_milestones(p.id)
            ],
        }
        notes = self.list_notes("plan", p.id)
        if notes:
            payload["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("plan", p.id)
        if comments:
            payload["comments"] = [vars(c) for c in comments]
        issue_refs = self.list_issue_links("plan", p.id)
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lpui show`: fields + criteria + links + repos + children."""
        with self._connect():
            if kind == "plan":
                p = self.get_plan(obj_id)
                return None if p is None else self._plan_show(p)
            if kind == "milestone":
                s = self.get_milestone(obj_id)
                return None if s is None else self._milestone_show(s)
            if kind == "task":
                t = self.get_task(obj_id)
                return None if t is None else self._task_show(t)
        raise ValueError(KIND_ERROR)

    def get_full_many(self, kind: str, obj_ids: list[int]) -> list[dict]:
        """Full context records for several rows, in the requested order."""
        with self._connect():
            reader = _FullReader(self)
            if kind == "plan":
                objects: dict[int, Plan | Milestone | Task] = {
                    plan.id: plan for plan in self.list_plans()
                }
            elif kind == "milestone":
                objects = {
                    milestone.id: milestone
                    for items in reader.milestones.values()
                    for milestone in items
                }
            elif kind == "task":
                objects = {task.id: task for items in reader.tasks.values() for task in items}
            else:
                raise ValueError(KIND_ERROR)
            out: list[dict] = []
            for obj_id in obj_ids:
                obj = objects.get(obj_id)
                if obj is None:
                    continue
                if isinstance(obj, Plan):
                    out.append(reader.plan(obj))
                elif isinstance(obj, Milestone):
                    out.append(reader.milestone(obj))
                else:
                    out.append(reader.task(obj))
            return out

    def status_events(self, kind: str) -> list[tuple[float, str]]:
        """(ts, detail) status moves for a kind, newest first (archive policy input)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind=? AND action='status' ORDER BY id DESC",
                (kind,),
            ).fetchall()
        return [(r["ts"], r["detail"]) for r in rows]

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]:
        """Latest 'plan #id -> status' event per plan, keyed by plan id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind='plan' AND action='status'"
                " ORDER BY id DESC"
            ).fetchall()
        out: dict[int, tuple[float, str]] = {}
        for row in rows:
            detail = str(row["detail"] or "").removesuffix(" (rollup)")
            if not detail.startswith("plan #"):
                continue
            body = detail[len("plan #") :]
            try:
                plan_text, target = body.split(" -> ", 1)
                plan_id = int(plan_text)
            except ValueError:
                continue
            out.setdefault(plan_id, (float(row["ts"]), target))
        return out

    # -- status --------------------------------------------------------
    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool:
        """Raw status write, no healing or logging (see services)."""
        table = table_for(kind)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status.value, obj_id))
            return (cur.rowcount or 0) > 0

    def counts(self) -> dict[str, int]:
        """Plan, milestone, and task totals, plus per-state plan counts."""
        with self._connect() as conn:
            np = conn.execute("SELECT COUNT(*) c FROM plans").fetchone()["c"]
            ns = conn.execute("SELECT COUNT(*) c FROM milestones").fetchone()["c"]
            nt = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
            nd = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"]
            npt = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='todo'").fetchone()["c"]
            npd = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='doing'").fetchone()["c"]
            npn = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='done'").fetchone()["c"]
        return {
            "plans": np,
            "milestones": ns,
            "tasks": nt,
            "tasks_done": nd,
            "plans_todo": npt,
            "plans_doing": npd,
            "plans_done": npn,
        }


class _FullReader:
    """Build full show payloads from one set of bulk maps."""

    def __init__(self, store: Store) -> None:
        self.milestones = store.milestones_map()
        self.tasks = store.tasks_map()
        self.criteria = store.criteria_map()
        self.links = store.vcs_links_map()
        self.forge = store.forge_links_map()
        self.repos = store.repos_map()
        self.claims = store.claims_map()
        self.notes = store.notes_full_map()
        self.comments = store.comments_full_map()
        self.issues = store.issue_links_map()
        self.milestone_by_id = {
            milestone.id: milestone for items in self.milestones.values() for milestone in items
        }
        self.task_by_id = {task.id: task for items in self.tasks.values() for task in items}

    def _gate_state(self, task_id: int) -> dict:
        links = self.forge.get(("task", task_id), [])
        if not links:
            return {"prs": 0, "checks": "none", "state": "missing"}
        values = [str(link.checks or "none") for link in links]
        if any(value == "fail" for value in values):
            checks = "fail"
        elif any(value == "pending" for value in values):
            checks = "pending"
        elif all(value in {"pass", "neutral", "skipped"} for value in values):
            checks = "pass"
        else:
            checks = "none"
        return {
            "prs": len(links),
            "checks": checks,
            "state": "pass" if checks == "pass" else checks,
        }

    def _task_view(self, task: Task) -> dict:
        data = _ser(vars(task))
        claim = self.claims.get(task.id)
        if claim is not None:
            data["claim"] = vars(claim)
        notes = self.notes.get(("task", task.id), [])
        if notes:
            data["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("task", task.id), [])
        if comments:
            data["comments"] = [vars(comment) for comment in comments]
        gate = self._gate_state(task.id)
        if gate["prs"]:
            data["gate"] = gate
        issue_refs = self.issues.get(("task", task.id), [])
        if issue_refs:
            data["issues"] = issue_refs
        return data

    def _effective_links(self, kind: str, obj_id: int) -> list[VcsLink]:
        links = list(self.links.get((kind, obj_id), []))
        if kind == "milestone":
            for task in self.tasks.get(obj_id, ()):
                links.extend(self.links.get(("task", task.id), []))
        elif kind == "plan":
            for milestone in self.milestones.get(obj_id, ()):
                links.extend(self.links.get(("milestone", milestone.id), []))
                for task in self.tasks.get(milestone.id, ()):
                    links.extend(self.links.get(("task", task.id), []))
        seen: set[tuple[str, str]] = set()
        out: list[VcsLink] = []
        for link in links:
            key = (link.sha, link.repo_root)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def _effective_forge(self, kind: str, obj_id: int) -> list[ForgeLink]:
        links = list(self.forge.get((kind, obj_id), []))
        if kind == "milestone":
            for task in self.tasks.get(obj_id, ()):
                links.extend(self.forge.get(("task", task.id), []))
        elif kind == "plan":
            for milestone in self.milestones.get(obj_id, ()):
                links.extend(self.forge.get(("milestone", milestone.id), []))
                for task in self.tasks.get(milestone.id, ()):
                    links.extend(self.forge.get(("task", task.id), []))
        seen: set[tuple[str, str, int]] = set()
        out: list[ForgeLink] = []
        for link in links:
            key = (link.provider, link.kind, link.number)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def _effective_repos(self, kind: str, obj_id: int) -> list[dict]:
        explicit = self.repos.get((kind, obj_id), [])
        if explicit:
            return explicit
        if kind == "task":
            task = self.task_by_id.get(obj_id)
            if task is not None:
                return self._effective_repos("milestone", task.milestone_id)
        elif kind == "milestone":
            milestone = self.milestone_by_id.get(obj_id)
            if milestone is not None:
                return self.repos.get(("plan", milestone.plan_id), [])
        return []

    def task(self, task: Task) -> dict:
        return {
            "task": self._task_view(task),
            "criteria": [vars(item) for item in self.criteria.get(("task", task.id), [])],
            "links": [vars(item) for item in self.links.get(("task", task.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("task", task.id)],
            "forge_links": [vars(item) for item in self.forge.get(("task", task.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("task", task.id)
            ],
            "repos": self.repos.get(("task", task.id), []),
            "effective_repos": self._effective_repos("task", task.id),
        }

    def milestone(self, milestone: Milestone) -> dict:
        payload = {
            "milestone": _ser(vars(milestone)),
            "criteria": [vars(item) for item in self.criteria.get(("milestone", milestone.id), [])],
            "links": [vars(item) for item in self.links.get(("milestone", milestone.id), [])],
            "effective_links": [
                vars(item) for item in self._effective_links("milestone", milestone.id)
            ],
            "forge_links": [vars(item) for item in self.forge.get(("milestone", milestone.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("milestone", milestone.id)
            ],
            "repos": self.repos.get(("milestone", milestone.id), []),
            "effective_repos": self._effective_repos("milestone", milestone.id),
            "tasks": [
                {
                    "task": self._task_view(task),
                    "criteria": [vars(item) for item in self.criteria.get(("task", task.id), [])],
                }
                for task in self.tasks.get(milestone.id, ())
            ],
        }
        notes = self.notes.get(("milestone", milestone.id), [])
        if notes:
            payload["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("milestone", milestone.id), [])
        if comments:
            payload["comments"] = [vars(comment) for comment in comments]
        issue_refs = self.issues.get(("milestone", milestone.id), [])
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def plan(self, plan: Plan) -> dict:
        payload = {
            "plan": _ser(vars(plan)),
            "criteria": [vars(item) for item in self.criteria.get(("plan", plan.id), [])],
            "links": [vars(item) for item in self.links.get(("plan", plan.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("plan", plan.id)],
            "forge_links": [vars(item) for item in self.forge.get(("plan", plan.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("plan", plan.id)
            ],
            "repos": self.repos.get(("plan", plan.id), []),
            "effective_repos": self._effective_repos("plan", plan.id),
            "milestones": [
                {
                    "milestone": _ser(vars(milestone)),
                    "criteria": [
                        vars(item) for item in self.criteria.get(("milestone", milestone.id), [])
                    ],
                    "repos": self.repos.get(("milestone", milestone.id), []),
                    "effective_repos": self._effective_repos("milestone", milestone.id),
                    "tasks": [self._task_view(task) for task in self.tasks.get(milestone.id, ())],
                }
                for milestone in self.milestones.get(plan.id, ())
            ],
        }
        notes = self.notes.get(("plan", plan.id), [])
        if notes:
            payload["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("plan", plan.id), [])
        if comments:
            payload["comments"] = [vars(comment) for comment in comments]
        issue_refs = self.issues.get(("plan", plan.id), [])
        if issue_refs:
            payload["issues"] = issue_refs
        return payload
