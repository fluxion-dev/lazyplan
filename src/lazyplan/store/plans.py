"""Store methods for plans."""

from __future__ import annotations

import sqlite3
import uuid

from ..kinds import table_for
from ..models import (
    Milestone,
    Plan,
    Status,
)
from .base import (
    StoreBase,
)


class PlansMixin(StoreBase):
    """Plans persistence."""

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

    def _delete_milestone_repos(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove repo links under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        self._delete_entity_repos(conn, "milestone", milestone_id)
        for tid in tids:
            self._delete_entity_repos(conn, "task", tid)

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

    def _delete_milestone_comments(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove comments under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        self._delete_comments(conn, "milestone", milestone_id)
        for tid in tids:
            self._delete_comments(conn, "task", tid)

    def _delete_milestone_notes(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        """Remove notes under a milestone and its tasks."""
        tids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE milestone_id=?", (milestone_id,)
            ).fetchall()
        ]
        self._delete_notes(conn, "milestone", milestone_id)
        for tid in tids:
            self._delete_notes(conn, "task", tid)

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

    def _parent_exists(self, parent_kind: str, parent_id: int) -> bool:
        """True when the criteria parent row exists."""
        if parent_kind == "plan":
            return self.get_plan(parent_id) is not None
        if parent_kind == "milestone":
            return self.get_milestone(parent_id) is not None
        return self.get_task(parent_id) is not None
