"""Agent proposals awaiting human review."""

from __future__ import annotations

import json
import time
from typing import Any

from .base import StoreBase

PROPOSAL_KINDS = ("plan_document", "row_edit", "task_create")
PROPOSAL_STATUSES = ("pending", "applied", "rejected")


class ProposalsMixin(StoreBase):
    """Persist structural changes proposed by an agent, never applied here."""

    def add_proposal(
        self,
        kind: str,
        title: str,
        payload: dict[str, Any],
        *,
        summary: str = "",
        actor: str = "agent",
    ) -> dict[str, Any]:
        """Store one pending proposal and return it."""
        if kind not in PROPOSAL_KINDS:
            raise ValueError(f"unknown proposal kind {kind!r}")
        if not title.strip():
            raise ValueError("proposal title must not be empty")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO proposals (kind, title, summary, payload, created_at, actor)"
                " VALUES (?,?,?,?,?,?)",
                (kind, title.strip(), summary.strip(), json.dumps(payload), stamp, actor),
            )
            proposal_id = int(cur.lastrowid or 0)
            self.log(
                actor,
                "proposal",
                "add",
                f"proposal #{proposal_id} {title.strip()}",
            )
        row = self.get_proposal(proposal_id)
        assert row is not None
        return row

    def list_proposals(
        self,
        status: str = "pending",
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Proposals, newest first, filtered by status or `all`."""
        sql = "SELECT * FROM proposals"
        params: list[object] = []
        if status != "all":
            if status not in PROPOSAL_STATUSES:
                raise ValueError(f"unknown proposal status {status!r}")
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(int(limit), 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._proposal_row(row) for row in rows]

    def get_proposal(self, proposal_id: int) -> dict[str, Any] | None:
        """One proposal by id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return self._proposal_row(row) if row is not None else None

    def resolve_proposal(
        self,
        proposal_id: int,
        status: str,
        *,
        actor: str = "human",
    ) -> dict[str, Any]:
        """Mark a pending proposal applied or rejected."""
        if status not in ("applied", "rejected"):
            raise ValueError("proposal status must be applied or rejected")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if row is None:
                raise KeyError(f"proposal #{proposal_id} not found")
            if row["status"] != "pending":
                raise ValueError(f"proposal #{proposal_id} is already {row['status']}")
            conn.execute(
                "UPDATE proposals SET status=?, resolved_at=? WHERE id=?",
                (status, time.time(), proposal_id),
            )
            self.log(actor, "proposal", status, f"proposal #{proposal_id} {status}")
        resolved = self.get_proposal(proposal_id)
        assert resolved is not None
        return resolved

    @staticmethod
    def _proposal_row(row: Any) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = {}
        return {
            "id": int(row["id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "summary": str(row["summary"]),
            "payload": payload if isinstance(payload, dict) else {},
            "status": str(row["status"]),
            "actor": str(row["actor"]),
            "created_at": float(row["created_at"]),
            "resolved_at": float(row["resolved_at"]),
        }
