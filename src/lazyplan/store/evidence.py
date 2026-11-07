"""Store methods for the criterion evidence ledger."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace

from ..core.entities import CriterionEvidence
from ..core.policies.evidence import check_task
from .base import StoreBase


class EvidenceMixin(StoreBase):
    """Append-only proof rows attached to criteria."""

    @staticmethod
    def _row_to_evidence(r: sqlite3.Row) -> CriterionEvidence:
        """Row to CriterionEvidence."""
        return CriterionEvidence(
            id=int(r["id"]),
            criterion_id=int(r["criterion_id"]),
            task_id=int(r["task_id"]) if r["task_id"] is not None else None,
            command=str(r["command"]),
            exit_code=int(r["exit_code"]) if r["exit_code"] is not None else None,
            commit_sha=str(r["commit_sha"]),
            pr_url=str(r["pr_url"]),
            artifact_path=str(r["artifact_path"]),
            note=str(r["note"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
        )

    def add_evidence(
        self,
        criterion_id: int,
        command: str = "",
        exit_code: int | None = None,
        commit_sha: str = "",
        pr_url: str = "",
        artifact_path: str = "",
        note: str = "",
        task_id: int | None = None,
        actor: str = "human",
    ) -> CriterionEvidence:
        """Record one proof row; never runs the command or fetches the link."""
        if self.get_criterion(criterion_id) is None:
            raise KeyError(f"criterion #{criterion_id} not found")
        if task_id is not None:
            if self.get_task(task_id) is None:
                raise KeyError(f"task #{task_id} not found")
            check_task(task_id, [task.id for task in self.criterion_tasks(criterion_id)])
        row = CriterionEvidence(
            id=0,
            criterion_id=criterion_id,
            task_id=task_id,
            command=command,
            exit_code=exit_code,
            commit_sha=commit_sha,
            pr_url=pr_url,
            artifact_path=artifact_path,
            note=note,
            actor=actor,
            ts=time.time(),
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO criterion_evidence"
                " (criterion_id, task_id, command, exit_code, commit_sha, pr_url,"
                " artifact_path, note, actor, ts)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    row.criterion_id,
                    row.task_id,
                    row.command,
                    row.exit_code,
                    row.commit_sha,
                    row.pr_url,
                    row.artifact_path,
                    row.note,
                    row.actor,
                    row.ts,
                ),
            )
            row = replace(row, id=cur.lastrowid or 0)
        self.log(
            actor,
            "criterion",
            "evidence",
            f"criterion #{criterion_id} {'pass' if row.passing else 'fail'}",
        )
        return row

    def restore_evidence(
        self,
        criterion_id: int,
        task_id: int | None = None,
        command: str = "",
        exit_code: int | None = None,
        commit_sha: str = "",
        pr_url: str = "",
        artifact_path: str = "",
        note: str = "",
        actor: str = "human",
        ts: float = 0.0,
    ) -> CriterionEvidence | None:
        """Import one evidence row with its original timestamp; no feed event."""
        if self.get_criterion(criterion_id) is None:
            return None
        if task_id is not None and self.get_task(task_id) is None:
            task_id = None
        row = CriterionEvidence(
            id=0,
            criterion_id=criterion_id,
            task_id=task_id,
            command=command,
            exit_code=exit_code,
            commit_sha=commit_sha,
            pr_url=pr_url,
            artifact_path=artifact_path,
            note=note,
            actor=actor,
            ts=ts,
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO criterion_evidence"
                " (criterion_id, task_id, command, exit_code, commit_sha, pr_url,"
                " artifact_path, note, actor, ts)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    row.criterion_id,
                    row.task_id,
                    row.command,
                    row.exit_code,
                    row.commit_sha,
                    row.pr_url,
                    row.artifact_path,
                    row.note,
                    row.actor,
                    row.ts,
                ),
            )
            return replace(row, id=cur.lastrowid or 0)

    def list_evidence(self, criterion_id: int) -> list[CriterionEvidence]:
        """Evidence for one criterion, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criterion_evidence WHERE criterion_id=? ORDER BY id",
                (criterion_id,),
            ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def evidence_map(self) -> dict[int, list[CriterionEvidence]]:
        """Every evidence row grouped by criterion id, in id order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criterion_evidence ORDER BY criterion_id, id"
            ).fetchall()
        out: dict[int, list[CriterionEvidence]] = {}
        for row in rows:
            item = self._row_to_evidence(row)
            out.setdefault(item.criterion_id, []).append(item)
        return out
