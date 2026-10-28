"""Store methods for plans."""

from __future__ import annotations

import sqlite3

from ..models import (
    Status,
    Task,
)
from .base import (
    StoreBase,
)


class TasksMixin(StoreBase):
    """Store methods for plans."""

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
