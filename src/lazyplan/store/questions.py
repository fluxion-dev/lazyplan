"""Store methods for plan questions."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace

from ..core.entities import PlanQuestion
from ..core.policies.questions import validate_status, validate_text
from .base import StoreBase


class QuestionsMixin(StoreBase):
    """Open and resolved questions attached to a plan."""

    @staticmethod
    def _row_to_question(r: sqlite3.Row) -> PlanQuestion:
        """Row to PlanQuestion."""
        return PlanQuestion(
            id=int(r["id"]),
            plan_id=int(r["plan_id"]),
            text=str(r["text"]),
            status=str(r["status"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
            resolved_at=float(r["resolved_at"]),
            resolved_by=str(r["resolved_by"]),
            resolution=str(r["resolution"]),
        )

    def add_question(self, plan_id: int, text: str, actor: str = "human") -> PlanQuestion:
        """Add one open question; a duplicate open row is rejected."""
        body = validate_text(text)
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise KeyError(f"plan #{plan_id} not found")
            existing = conn.execute(
                "SELECT id FROM plan_questions WHERE plan_id=? AND text=? AND status='open'",
                (plan_id, body),
            ).fetchone()
            if existing is not None:
                raise ValueError(f"question already open as #{existing['id']}")
            stamp = time.time()
            cur = conn.execute(
                "INSERT INTO plan_questions (plan_id, text, status, actor, ts) VALUES (?,?,?,?,?)",
                (plan_id, body, "open", actor, stamp),
            )
            question_id = cur.lastrowid or 0
        self.log(actor, "plan", "question", f"Q#{question_id} plan #{plan_id}")
        return PlanQuestion(
            id=question_id,
            plan_id=plan_id,
            text=body,
            actor=actor,
            ts=stamp,
        )

    def restore_question(
        self,
        plan_id: int,
        text: str,
        status: str = "open",
        actor: str = "human",
        ts: float = 0.0,
        resolved_at: float = 0.0,
        resolved_by: str = "",
        resolution: str = "",
    ) -> PlanQuestion | None:
        """Import one question with its original state and timestamps."""
        if self.get_plan(plan_id) is None:
            return None
        row = PlanQuestion(
            id=0,
            plan_id=plan_id,
            text=text,
            status=status,
            actor=actor,
            ts=ts,
            resolved_at=resolved_at,
            resolved_by=resolved_by,
            resolution=resolution,
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO plan_questions"
                " (plan_id, text, status, actor, ts, resolved_at, resolved_by, resolution)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    row.plan_id,
                    row.text,
                    row.status,
                    row.actor,
                    row.ts,
                    row.resolved_at,
                    row.resolved_by,
                    row.resolution,
                ),
            )
            return replace(row, id=cur.lastrowid or 0)

    def get_question(self, qid: int) -> PlanQuestion | None:
        """Fetch one question."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plan_questions WHERE id=?", (qid,)).fetchone()
        return self._row_to_question(row) if row is not None else None

    def list_questions(self, plan_id: int, status: str = "open") -> list[PlanQuestion]:
        """Questions for one plan, in creation order."""
        if status != "all":
            validate_status(status)
        with self._connect() as conn:
            if status == "all":
                rows = conn.execute(
                    "SELECT * FROM plan_questions WHERE plan_id=? ORDER BY id",
                    (plan_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plan_questions WHERE plan_id=? AND status=? ORDER BY id",
                    (plan_id, status),
                ).fetchall()
        return [self._row_to_question(row) for row in rows]

    def questions_map(self) -> dict[int, list[PlanQuestion]]:
        """Every question grouped by plan id, in creation order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM plan_questions ORDER BY plan_id, id").fetchall()
        out: dict[int, list[PlanQuestion]] = {}
        for row in rows:
            item = self._row_to_question(row)
            out.setdefault(item.plan_id, []).append(item)
        return out

    def resolve_question(
        self, qid: int, note: str = "", actor: str = "human"
    ) -> PlanQuestion | None:
        """Mark one question resolved and keep the answer."""
        question = self.get_question(qid)
        if question is None or question.status == "resolved":
            return question
        stamp = time.time()
        body = note.strip()
        with self._connect() as conn:
            conn.execute(
                "UPDATE plan_questions"
                " SET status='resolved', resolved_at=?, resolved_by=?, resolution=?"
                " WHERE id=?",
                (stamp, actor, body, qid),
            )
        self.log(actor, "plan", "question-resolve", f"Q#{qid}")
        return replace(
            question,
            status="resolved",
            resolved_at=stamp,
            resolved_by=actor,
            resolution=body,
        )

    def reopen_question(
        self, qid: int, note: str = "", actor: str = "human"
    ) -> PlanQuestion | None:
        """Reopen one question and record why on the plan."""
        question = self.get_question(qid)
        if question is None or question.status == "open":
            return question
        reason = note.strip()
        text = f"Question #{qid} reopened" + (f": {reason}" if reason else "")
        with self.transaction():
            with self._connect() as conn:
                conn.execute(
                    "UPDATE plan_questions"
                    " SET status='open', resolved_at=0, resolved_by='', resolution=''"
                    " WHERE id=?",
                    (qid,),
                )
            self.add_note("plan", question.plan_id, text, actor=actor)
            self.log(actor, "plan", "question-reopen", f"Q#{qid}")
        return replace(
            question,
            status="open",
            resolved_at=0.0,
            resolved_by="",
            resolution="",
        )
