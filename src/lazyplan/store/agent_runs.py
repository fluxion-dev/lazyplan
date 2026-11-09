"""Agent-run records linking ACP sessions to lazyplan work."""

from __future__ import annotations

import time
from typing import Any

from .base import StoreBase


class AgentRunsMixin(StoreBase):
    """One row per workbench conversation."""

    def add_agent_run(
        self,
        agent_session_id: str,
        *,
        lazyplan_session_id: int | None = None,
        plan_id: int | None = None,
        task_id: int | None = None,
        title: str = "",
        cwd: str = "",
        actor: str = "agent",
    ) -> dict[str, Any]:
        """Record one started ACP conversation."""
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agent_runs"
                " (agent_session_id, lazyplan_session_id, plan_id, task_id,"
                " title, cwd, started_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    agent_session_id,
                    lazyplan_session_id,
                    plan_id,
                    task_id,
                    title,
                    cwd,
                    stamp,
                ),
            )
            run_id = int(cur.lastrowid or 0)
            self.log(actor, "agent_run", "start", f"agent run #{run_id} {title}".strip())
        row = self.get_agent_run(run_id)
        assert row is not None
        return row

    def get_agent_run(self, run_id: int) -> dict[str, Any] | None:
        """One agent run by id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        return self._agent_run_row(row) if row is not None else None

    def list_agent_runs(
        self,
        *,
        status: str = "running",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Agent runs, newest first."""
        sql = "SELECT * FROM agent_runs"
        params: list[object] = []
        if status != "all":
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(int(limit), 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._agent_run_row(row) for row in rows]

    def end_agent_run(
        self,
        run_id: int,
        *,
        status: str = "done",
        summary: str = "",
        handoff: str = "",
        actor: str = "human",
    ) -> dict[str, Any]:
        """Close one agent run with a summary and handoff."""
        if status not in ("idle", "done", "error"):
            raise ValueError("agent run status must be idle, done, or error")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"agent run #{run_id} not found")
            conn.execute(
                "UPDATE agent_runs SET status=?, ended_at=?, summary=?, handoff=? WHERE id=?",
                (status, time.time(), summary.strip(), handoff.strip(), run_id),
            )
            self.log(actor, "agent_run", status, f"agent run #{run_id} {status}")
        ended = self.get_agent_run(run_id)
        assert ended is not None
        return ended

    @staticmethod
    def _agent_run_row(row: Any) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "agent_session_id": str(row["agent_session_id"]),
            "lazyplan_session_id": row["lazyplan_session_id"],
            "plan_id": row["plan_id"],
            "task_id": row["task_id"],
            "title": str(row["title"]),
            "cwd": str(row["cwd"]),
            "status": str(row["status"]),
            "started_at": float(row["started_at"]),
            "ended_at": float(row["ended_at"]),
            "summary": str(row["summary"]),
            "handoff": str(row["handoff"]),
        }
