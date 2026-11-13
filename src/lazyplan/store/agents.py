"""Store methods for the live agent registry and its transition log."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Sequence

from ..core.entities import Agent, AgentEvent
from ..core.policies.agents import can_transition, normalize_status
from .base import StoreBase


def _optional_id(value: object) -> int | None:
    """Nullable foreign key as an int, or None."""
    return None if value is None else int(str(value))


_IDENTITY_FIELDS = (
    "host",
    "host_session",
    "agent",
    "role",
    "model",
    "parent_id",
    "pid",
    "process_start",
    "repo_path",
    "worktree",
    "branch",
    "head_sha",
    "plan_id",
    "task_id",
    "unbound_reason",
)


class AgentsMixin(StoreBase):
    """Register, transition, read, and archive exact host agents."""

    @staticmethod
    def _row_to_agent(row: sqlite3.Row) -> Agent:
        """Map one sqlite row to the entity."""
        return Agent(
            id=int(row["id"]),
            host=str(row["host"]),
            host_session=str(row["host_session"]),
            agent=str(row["agent"]),
            role=str(row["role"]),
            model=str(row["model"]),
            parent_id=_optional_id(row["parent_id"]),
            pid=int(row["pid"]),
            process_start=str(row["process_start"]),
            repo_path=str(row["repo_path"]),
            worktree=str(row["worktree"]),
            branch=str(row["branch"]),
            head_sha=str(row["head_sha"]),
            plan_id=_optional_id(row["plan_id"]),
            task_id=_optional_id(row["task_id"]),
            status=str(row["status"]),
            unbound_reason=str(row["unbound_reason"]),
            started_at=float(row["started_at"]),
            updated_at=float(row["updated_at"]),
            ended_at=float(row["ended_at"]),
            summary=str(row["summary"]),
            handoff=str(row["handoff"]),
            archived_at=float(row["archived_at"]),
        )

    @staticmethod
    def _row_to_agent_event(row: sqlite3.Row) -> AgentEvent:
        """Map one transition row to the entity."""
        return AgentEvent(
            id=int(row["id"]),
            agent_id=int(row["agent_id"]),
            ts=float(row["ts"] or 0),
            event=str(row["event"] or ""),
            from_status=str(row["from_status"] or ""),
            to_status=str(row["to_status"] or ""),
            detail=str(row["detail"] or ""),
        )

    def _check_binding(self, plan_id: int | None, task_id: int | None) -> None:
        """Validate that a plan and task exist and belong together."""
        if plan_id is None:
            if task_id is not None:
                raise ValueError("a bound task needs a plan")
            return
        with self._connect() as conn:
            plan = conn.execute("SELECT id FROM plans WHERE id=?", (plan_id,)).fetchone()
            if plan is None:
                raise KeyError(f"plan #{plan_id} not found")
            if task_id is None:
                return
            row = conn.execute(
                "SELECT t.id FROM tasks t"
                " JOIN milestones m ON m.id=t.milestone_id"
                " WHERE t.id=? AND m.plan_id=?",
                (task_id, plan_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"task T{task_id} is not in plan P{plan_id}")

    def add_agent(
        self,
        actor: str,
        host: str = "unknown",
        host_session: str = "",
        agent: str = "unknown",
        role: str = "primary",
        model: str = "unknown",
        parent_id: int | None = None,
        pid: int = 0,
        process_start: str = "",
        repo_path: str = "",
        worktree: str = "",
        branch: str = "",
        head_sha: str = "",
        plan_id: int | None = None,
        task_id: int | None = None,
        status: str = "starting",
        unbound_reason: str = "",
        note: str = "",
        now: float | None = None,
    ) -> Agent:
        """Insert one registered agent and its first transition."""
        stamp = time.time() if now is None else now
        state = normalize_status(status)
        self._check_binding(plan_id, task_id)
        if parent_id is not None and self.get_agent(parent_id) is None:
            raise KeyError(f"parent agent A{parent_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO agents"
                " (host, host_session, agent, role, model, parent_id, pid, process_start,"
                " repo_path, worktree, branch, head_sha, plan_id, task_id, status,"
                " unbound_reason, started_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    host,
                    host_session,
                    agent,
                    role,
                    model,
                    parent_id,
                    pid,
                    process_start,
                    repo_path,
                    worktree,
                    branch,
                    head_sha,
                    plan_id,
                    task_id,
                    state,
                    unbound_reason,
                    stamp,
                    stamp,
                ),
            )
            agent_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO agent_events (agent_id, ts, event, from_status, to_status, detail)"
                " VALUES (?,?,?,?,?,?)",
                (agent_id, stamp, "start", "", state, note[:500]),
            )
        self.log(actor, "agent", "start", f"agent A{agent_id} {host} started", now=stamp)
        row = self.get_agent(agent_id)
        assert row is not None
        return row

    def get_agent(self, agent_id: int) -> Agent | None:
        """One agent by id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return self._row_to_agent(row) if row is not None else None

    def patch_agent(self, agent_id: int, now: float | None = None, **fields: object) -> Agent:
        """Refresh exact identity facts without recording a transition."""
        unknown = set(fields) - set(_IDENTITY_FIELDS)
        if unknown:
            raise ValueError(f"unknown agent fields: {', '.join(sorted(unknown))}")
        stamp = time.time() if now is None else now
        if "plan_id" in fields or "task_id" in fields:
            current = self.get_agent(agent_id)
            if current is None:
                raise KeyError(f"agent A{agent_id} not found")
            plan = fields.get("plan_id", current.plan_id)
            task = fields.get("task_id", current.task_id)
            self._check_binding(
                None if plan is None else int(str(plan)), None if task is None else int(str(task))
            )
        sets = ", ".join(f"{name}=?" for name in fields)
        params: list[object] = list(fields.values())
        params.extend([stamp, agent_id])
        with self._connect() as conn:
            conn.execute(f"UPDATE agents SET {sets}, updated_at=? WHERE id=?", params)
        row = self.get_agent(agent_id)
        if row is None:
            raise KeyError(f"agent A{agent_id} not found")
        return row

    def transition_agent(
        self,
        agent_id: int,
        status: str,
        event: str = "",
        detail: str = "",
        summary: str = "",
        handoff: str = "",
        now: float | None = None,
    ) -> Agent:
        """Move one agent through an allowed transition and log one event row."""
        stamp = time.time() if now is None else now
        target = normalize_status(status)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
            if row is None:
                raise KeyError(f"agent A{agent_id} not found")
            current = str(row["status"])
            if not can_transition(current, target):
                raise ValueError(f"agent A{agent_id} cannot move {current} -> {target}")
            sets = ["status=?", "updated_at=?"]
            params: list[object] = [target, stamp]
            if summary:
                sets.append("summary=?")
                params.append(summary)
            if handoff:
                sets.append("handoff=?")
                params.append(handoff)
            if target == "ended" and int(row["ended_at"] or 0) == 0:
                sets.append("ended_at=?")
                params.append(stamp)
            params.append(agent_id)
            conn.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id=?", params)
            conn.execute(
                "INSERT INTO agent_events (agent_id, ts, event, from_status, to_status, detail)"
                " VALUES (?,?,?,?,?,?)",
                (agent_id, stamp, event[:64], current, target, detail[:500]),
            )
        if target in ("lost", "ended"):
            verb = "lost" if target == "lost" else "ended"
            self.log("agent", "agent", verb, f"agent A{agent_id} {verb}", now=stamp)
        result = self.get_agent(agent_id)
        assert result is not None
        return result

    def list_agents(
        self,
        plan_id: int | None = None,
        task_id: int | None = None,
        open_only: bool = False,
        live_only: bool = False,
        host: str = "",
        status: str = "",
        limit: int = 50,
        archived: str = "hide",
    ) -> list[Agent]:
        """Recent agents, newest first, with optional registry filters."""
        sql = "SELECT * FROM agents"
        clauses: list[str] = []
        params: list[object] = []
        if plan_id is not None:
            clauses.append("plan_id=?")
            params.append(plan_id)
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(task_id)
        if open_only:
            clauses.append("ended_at=0")
        if live_only:
            clauses.append("status NOT IN ('lost','ended') AND ended_at=0")
        if host:
            clauses.append("host=?")
            params.append(host)
        if status:
            clauses.append("status=?")
            params.append(normalize_status(status))
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
        return [self._row_to_agent(row) for row in rows]

    def agents_for_host(
        self,
        host: str,
        host_session: str,
        open_only: bool = True,
    ) -> list[Agent]:
        """Agents registered for one host session, oldest first."""
        sql = "SELECT * FROM agents WHERE host=? AND host_session=?"
        if open_only:
            sql += " AND ended_at=0"
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, (host, host_session)).fetchall()
        return [self._row_to_agent(row) for row in rows]

    def child_agents(self, parent_id: int, open_only: bool = False) -> list[Agent]:
        """Agents whose parent is one row, oldest first."""
        sql = "SELECT * FROM agents WHERE parent_id=?"
        if open_only:
            sql += " AND ended_at=0"
        sql += " ORDER BY id"
        with self._connect() as conn:
            rows = conn.execute(sql, (parent_id,)).fetchall()
        return [self._row_to_agent(row) for row in rows]

    def open_agents_with_pids(self) -> list[Agent]:
        """Open rows that carry a process id, for the liveness sweep."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agents WHERE ended_at=0 AND pid>0"
                " AND status NOT IN ('lost','ended') ORDER BY id"
            ).fetchall()
        return [self._row_to_agent(row) for row in rows]

    def end_agent(
        self,
        agent_id: int,
        actor: str,
        summary: str = "",
        handoff: str = "",
        now: float | None = None,
    ) -> Agent:
        """End one agent and every live child that points at it."""
        stamp = time.time() if now is None else now
        current = self.get_agent(agent_id)
        if current is None:
            raise KeyError(f"agent A{agent_id} not found")
        if current.status == "ended":
            raise ValueError(f"agent A{agent_id} has already ended")
        ended = self.transition_agent(
            agent_id,
            "ended",
            event="session-end",
            detail="ended by host" if not summary else summary,
            summary=summary,
            handoff=handoff,
            now=stamp,
        )
        for child in self.child_agents(agent_id, open_only=True):
            self.transition_agent(
                child.id,
                "ended",
                event="parent-end",
                detail=f"parent A{agent_id} ended",
                summary=f"parent A{agent_id} ended",
                now=stamp,
            )
        return ended

    def latest_ended_agent(
        self,
        plan_id: int | None = None,
        actor: str = "",
        repo_path: str = "",
    ) -> Agent | None:
        """Most recently ended, unarchived agent for a plan or checkout."""
        sql = "SELECT * FROM agents WHERE status='ended' AND archived_at=0"
        params: list[object] = []
        if plan_id is not None:
            sql += " AND plan_id=?"
            params.append(plan_id)
        if actor:
            sql += " AND agent=?"
            params.append(actor)
        if repo_path:
            sql += " AND repo_path=?"
            params.append(repo_path)
        sql += " ORDER BY ended_at DESC, id DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._row_to_agent(row) if row is not None else None

    def agent_events(self, agent_id: int, limit: int = 50) -> list[AgentEvent]:
        """Newest transitions for one agent."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE agent_id=? ORDER BY id DESC LIMIT ?",
                (agent_id, max(int(limit), 1)),
            ).fetchall()
        return [self._row_to_agent_event(row) for row in rows]

    def agent_event_counts(self, agent_id: int) -> dict[str, int]:
        """Transition counts by event name for one agent."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event, COUNT(*) AS n FROM agent_events WHERE agent_id=?"
                " GROUP BY event ORDER BY event",
                (agent_id,),
            ).fetchall()
        return {str(row["event"]): int(row["n"]) for row in rows}

    def archive_agents(
        self,
        agent_ids: Sequence[int],
        actor: str = "human",
        now: float | None = None,
    ) -> int:
        """Archive ended agents; open and lost rows are never archived."""
        stamp = time.time() if now is None else now
        archived = 0
        with self._connect() as conn:
            for agent_id in agent_ids:
                cur = conn.execute(
                    "UPDATE agents SET archived_at=?"
                    " WHERE id=? AND status='ended' AND archived_at=0",
                    (stamp, agent_id),
                )
                if (cur.rowcount or 0) == 0:
                    continue
                archived += 1
        if archived:
            self.log(actor, "agent", "archive", f"archived {archived} agent row(s)", now=stamp)
        return archived

    def restore_agent(self, agent_id: int, actor: str = "human", now: float | None = None) -> bool:
        """Clear one agent's archive stamp; a live row writes no event."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE agents SET archived_at=0 WHERE id=? AND archived_at<>0",
                (agent_id,),
            )
            changed = (cur.rowcount or 0) > 0
        if changed:
            self.log(actor, "agent", "restore", f"agent A{agent_id} restored", now=stamp)
        return changed

    def agent_counts(self) -> dict[str, int]:
        """Open agents by status, for the tracker subtitle."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM agents WHERE ended_at=0"
                " GROUP BY status ORDER BY status"
            ).fetchall()
        return {str(row["status"]): int(row["n"]) for row in rows}
