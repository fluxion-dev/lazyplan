"""SQLite persistence. Stdlib only. Shared by TUI and `lpui` CLI (agent ingress)."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from .kinds import KIND_ERROR, check_parent_kind, table_for
from .migrate import migrate
from .models import (
    PRIORITY_RANK,
    Criterion,
    Milestone,
    Plan,
    Status,
    Task,
    VcsLink,
    check_priority,
)
from .repo import ensure_plan_dir, resolve_db_path


def _ser(d: dict) -> dict:
    """JSON/agent-safe: Status -> value."""
    d = dict(d)
    if isinstance(d.get("status"), Status):
        d["status"] = d["status"].value
    return d


def _actor(explicit: str = "") -> str:
    """Normalize an actor name, defaulting to $USER or human."""
    if explicit.strip():
        return explicit.strip()[:64]
    return (os.environ.get("USER", "") or "human")[:64]


class Store:
    """SQLite persistence shared by the TUI and the lpui CLI."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = resolve_db_path(path)
        ensure_plan_dir(self.path)
        with self._connect() as conn:
            migrate(conn)

    def _connect(self) -> sqlite3.Connection:
        """Open a row-factory connection with foreign keys on."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

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
        return (mtime, c["plans"], c["milestones"], c["tasks"], mp, ms, mt, me, mc, ml)

    # -- plans ------------------------------------------------------
    def add_plan(
        self,
        name: str,
        description: str = "",
        goal: str = "",
        priority: str = "",
        actor: str = "human",
    ) -> Plan:
        """Insert a plan row and log the event (no template fill; see services)."""
        p = Plan(
            id=0,
            name=name.strip(),
            description=description,
            goal=goal,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO plans (name, description, status, goal, priority) VALUES (?,?,?,?,?)",
                (p.name, p.description, p.status.value, p.goal, p.priority),
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
            priority=self._opt(r, keys, "priority"),
        )

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

    def update_plan(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        priority: str | None = None,
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
        if priority is not None:
            p.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE plans SET name=?, description=?, goal=?, priority=? WHERE id=?",
                (p.name, p.description, p.goal, p.priority, pid),
            )
        self.log(actor, "plan", "edit", f"P#{pid} {p.name}")
        return p

    # -- milestones -------------------------------------------------------
    def add_milestone(
        self,
        plan_id: int,
        title: str,
        description: str = "",
        priority: str = "",
        actor: str = "human",
    ) -> Milestone:
        """Insert a milestone row and log the event (no template fill; see services)."""
        s = Milestone(
            id=0,
            plan_id=plan_id,
            title=title.strip(),
            description=description,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise KeyError(f"plan #{plan_id} not found")
            cur = conn.execute(
                "INSERT INTO milestones (plan_id, title, description, status, priority)"
                " VALUES (?,?,?,?,?)",
                (s.plan_id, s.title, s.description, s.status.value, s.priority),
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
            priority=self._opt(r, keys, "priority"),
        )

    def get_milestone(self, sid: int) -> Milestone | None:
        """Fetch a milestone by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM milestones WHERE id=?", (sid,)).fetchone()
        return self._row_to_milestone(r) if r is not None else None

    def list_milestones(self, plan_id: int) -> list[Milestone]:
        """Milestones of a plan, priority then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM milestones WHERE plan_id=? ORDER BY id", (plan_id,)
            ).fetchall()
        out = [self._row_to_milestone(r) for r in rows]
        out.sort(key=lambda s: (PRIORITY_RANK.get(s.priority, 99), s.id))
        return out

    def update_milestone(
        self,
        sid: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
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
        if priority is not None:
            s.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE milestones SET title=?, description=?, priority=? WHERE id=?",
                (s.title, s.description, s.priority, sid),
            )
        self.log(actor, "milestone", "edit", f"M#{sid} {s.title}")
        return s

    # -- tasks ---------------------------------------------------------
    def add_task(
        self,
        milestone_id: int,
        title: str,
        description: str = "",
        priority: str = "",
        actor: str = "human",
    ) -> Task:
        """Insert a task row and log the event (no template fill; see services)."""
        t = Task(
            id=0,
            milestone_id=milestone_id,
            title=title.strip(),
            description=description,
            priority=check_priority(priority),
        )
        with self._connect() as conn:
            if (
                conn.execute("SELECT 1 FROM milestones WHERE id=?", (milestone_id,)).fetchone()
                is None
            ):
                raise KeyError(f"milestone #{milestone_id} not found")
            cur = conn.execute(
                "INSERT INTO tasks (milestone_id, title, status, description, priority)"
                " VALUES (?,?,?,?,?)",
                (t.milestone_id, t.title, t.status.value, t.description, t.priority),
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
            priority=self._opt(r, keys, "priority"),
        )

    def get_task(self, tid: int) -> Task | None:
        """Fetch a task by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        return self._row_to_task(r) if r is not None else None

    def list_tasks(self, milestone_id: int) -> list[Task]:
        """Tasks of a milestone, priority then id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE milestone_id=? ORDER BY id", (milestone_id,)
            ).fetchall()
        out = [self._row_to_task(r) for r in rows]
        out.sort(key=lambda t: (PRIORITY_RANK.get(t.priority, 99), t.id))
        return out

    def update_task(
        self,
        tid: int,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
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
        if priority is not None:
            t.priority = check_priority(priority)
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET title=?, description=?, priority=? WHERE id=?",
                (t.title, t.description, t.priority, tid),
            )
        self.log(actor, "task", "edit", f"T#{tid} {t.title}")
        return t

    def delete(self, kind: str, obj_id: int, actor: str = "human") -> bool:
        """Delete a row and its subtree (criteria/links purged manually; FK cascades the rest)."""
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
                for sid in sids:
                    self._delete_milestone_criteria(conn, sid)
                    self._delete_milestone_links(conn, sid)
            elif kind == "milestone":
                self._delete_milestone_criteria(conn, obj_id)
                self._delete_milestone_links(conn, obj_id)
            else:
                conn.execute(
                    "DELETE FROM criteria WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
                conn.execute(
                    "DELETE FROM vcs_links WHERE parent_kind='task' AND parent_id=?", (obj_id,)
                )
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

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]:
        """Checklist items of a plan, milestone, or task."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criteria WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [
            Criterion(
                id=r["id"],
                parent_kind=r["parent_kind"],
                parent_id=r["parent_id"],
                text=r["text"],
                done=bool(r["done"]),
            )
            for r in rows
        ]

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
        )
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO vcs_links"
                " (parent_kind, parent_id, sha, subject, author, timestamp, repo_root)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    link.parent_kind,
                    link.parent_id,
                    link.sha,
                    link.subject,
                    link.author,
                    link.timestamp,
                    link.repo_root,
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

    def links_map(self) -> dict[tuple[str, int], list[str]]:
        """Every linked SHA grouped by (parent_kind, parent_id), oldest first.

        One query per call so tree renders stay O(1) in queries.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT parent_kind, parent_id, sha FROM vcs_links ORDER BY id"
            ).fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for r in rows:
            out.setdefault((r["parent_kind"], r["parent_id"]), []).append(r["sha"])
        return out

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
    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lpui show`: fields + criteria + links + children."""
        if kind == "plan":
            p = self.get_plan(obj_id)
            if p is None:
                return None
            return {
                "plan": _ser(vars(p)),
                "criteria": [vars(c) for c in self.list_criteria("plan", p.id)],
                "links": [vars(c) for c in self.list_links("plan", p.id)],
                "milestones": [
                    {
                        "milestone": _ser(vars(s)),
                        "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
                        "tasks": [_ser(vars(t)) for t in self.list_tasks(s.id)],
                    }
                    for s in self.list_milestones(p.id)
                ],
            }
        if kind == "milestone":
            s = self.get_milestone(obj_id)
            if s is None:
                return None
            return {
                "milestone": _ser(vars(s)),
                "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
                "links": [vars(c) for c in self.list_links("milestone", s.id)],
                "tasks": [
                    {
                        "task": _ser(vars(t)),
                        "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                    }
                    for t in self.list_tasks(s.id)
                ],
            }
        if kind == "task":
            t = self.get_task(obj_id)
            if t is None:
                return None
            return {
                "task": _ser(vars(t)),
                "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
                "links": [vars(c) for c in self.list_links("task", t.id)],
            }
        raise ValueError(KIND_ERROR)

    def status_events(self, kind: str) -> list[tuple[float, str]]:
        """(ts, detail) status moves for a kind, newest first (archive policy input)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind=? AND action='status' ORDER BY id DESC",
                (kind,),
            ).fetchall()
        return [(r["ts"], r["detail"]) for r in rows]

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
