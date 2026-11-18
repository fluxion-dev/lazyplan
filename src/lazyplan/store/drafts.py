"""Store methods for plan drafts and their revision snapshots."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace

from ..core.entities import DraftRevision, PlanDraft
from ..core.kinds import DRAFT_STATUSES
from .base import StoreBase


class DraftsMixin(StoreBase):
    """Plan-document drafts kept outside the plan queue."""

    @staticmethod
    def _row_to_draft(r: sqlite3.Row) -> PlanDraft:
        """Row to PlanDraft."""
        plan_id = r["plan_id"]
        return PlanDraft(
            id=int(r["id"]),
            title=str(r["title"]),
            document=str(r["document"]),
            status=str(r["status"]),
            revision=int(r["revision"]),
            actor=str(r["actor"]),
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
            plan_id=None if plan_id is None else int(plan_id),
            promoted_at=float(r["promoted_at"]),
        )

    @staticmethod
    def _row_to_draft_revision(r: sqlite3.Row) -> DraftRevision:
        """Row to DraftRevision."""
        return DraftRevision(
            id=int(r["id"]),
            draft_id=int(r["draft_id"]),
            revision=int(r["revision"]),
            document=str(r["document"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
            note=str(r["note"]),
        )

    def add_draft(
        self,
        title: str,
        document: str,
        actor: str = "human",
        status: str = "review",
        now: float | None = None,
    ) -> PlanDraft:
        """Store a draft and its first revision."""
        stamp = time.time() if now is None else now
        draft = PlanDraft(
            id=0,
            title=title.strip(),
            document=document.strip(),
            status=status,
            actor=actor,
            created_at=stamp,
            updated_at=stamp,
        )
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO plan_drafts"
                " (title, status, document, revision, actor, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    draft.title,
                    draft.status,
                    draft.document,
                    draft.revision,
                    actor,
                    stamp,
                    stamp,
                ),
            )
            draft_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO plan_draft_revisions"
                " (draft_id, revision, document, actor, ts, note)"
                " VALUES (?,?,?,?,?,?)",
                (draft_id, draft.revision, draft.document, actor, stamp, ""),
            )
        self.log(actor, "draft", "add", f"D#{draft_id} {draft.title[:80]}")
        return replace(draft, id=draft_id)

    def get_draft(self, draft_id: int) -> PlanDraft | None:
        """Fetch one draft by id."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft_id,)).fetchone()
        return self._row_to_draft(row) if row is not None else None

    def list_drafts(self, status: str = "all") -> list[PlanDraft]:
        """Drafts in creation order, optionally filtered by status."""
        if status != "all" and status not in DRAFT_STATUSES:
            raise ValueError(f"draft status must be all|{'|'.join(DRAFT_STATUSES)}")
        with self._connect() as conn:
            if status == "all":
                rows = conn.execute("SELECT * FROM plan_drafts ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM plan_drafts WHERE status=? ORDER BY id", (status,)
                ).fetchall()
        return [self._row_to_draft(row) for row in rows]

    def add_draft_revision(
        self,
        draft_id: int,
        document: str,
        actor: str = "human",
        note: str = "",
        title: str = "",
        expected_revision: int | None = None,
        now: float | None = None,
    ) -> tuple[PlanDraft, DraftRevision]:
        """Append the next document revision, refusing a stale base."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft_id,)).fetchone()
            if row is None:
                raise KeyError(f"draft #{draft_id} not found")
            current = int(row["revision"])
            if expected_revision is not None and current != expected_revision:
                raise ValueError(
                    f"draft #{draft_id} is at revision {current}, not {expected_revision}"
                )
            revision = current + 1
            title_text = title.strip() or str(row["title"])
            draft = PlanDraft(
                id=draft_id,
                title=title_text,
                document=document.strip(),
                status=str(row["status"]),
                revision=revision,
                actor=actor,
                created_at=float(row["created_at"]),
                updated_at=stamp,
                plan_id=None if row["plan_id"] is None else int(row["plan_id"]),
                promoted_at=float(row["promoted_at"]),
            )
            conn.execute(
                "UPDATE plan_drafts SET title=?, document=?, revision=?, updated_at=? WHERE id=?",
                (draft.title, draft.document, draft.revision, stamp, draft_id),
            )
            cur = conn.execute(
                "INSERT INTO plan_draft_revisions"
                " (draft_id, revision, document, actor, ts, note)"
                " VALUES (?,?,?,?,?,?)",
                (draft_id, revision, draft.document, actor, stamp, note.strip()),
            )
            revision_id = int(cur.lastrowid or 0)
        self.log(actor, "draft", "revise", f"D#{draft_id} r{revision}")
        snapshot = DraftRevision(
            id=revision_id,
            draft_id=draft_id,
            revision=revision,
            document=draft.document,
            actor=actor,
            ts=stamp,
            note=note.strip(),
        )
        return draft, snapshot

    def get_draft_revision(self, draft_id: int, revision: int) -> DraftRevision | None:
        """Fetch one draft snapshot."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plan_draft_revisions WHERE draft_id=? AND revision=?",
                (draft_id, revision),
            ).fetchone()
        return self._row_to_draft_revision(row) if row is not None else None

    def list_draft_revisions(self, draft_id: int) -> list[DraftRevision]:
        """Every snapshot for one draft, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plan_draft_revisions WHERE draft_id=? ORDER BY revision",
                (draft_id,),
            ).fetchall()
        return [self._row_to_draft_revision(row) for row in rows]

    def set_draft_status(
        self, draft_id: int, status: str, actor: str = "human", now: float | None = None
    ) -> PlanDraft | None:
        """Move one draft between review and revising."""
        if status not in DRAFT_STATUSES:
            raise ValueError(f"draft status must be {'|'.join(DRAFT_STATUSES)}")
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft_id,)).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE plan_drafts SET status=?, updated_at=? WHERE id=?",
                (status, stamp, draft_id),
            )
        self.log(actor, "draft", "status", f"D#{draft_id} {status}")
        return replace(self._row_to_draft(row), status=status, updated_at=stamp)

    def link_draft_plan(
        self, draft_id: int, plan_id: int, actor: str = "human", now: float | None = None
    ) -> PlanDraft | None:
        """Mark one draft promoted and record the plan it created."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM plan_drafts WHERE id=?", (draft_id,)).fetchone()
            if row is None:
                return None
            if conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise KeyError(f"plan #{plan_id} not found")
            conn.execute(
                "UPDATE plan_drafts"
                " SET status='promoted', plan_id=?, promoted_at=?, updated_at=?"
                " WHERE id=?",
                (plan_id, stamp, stamp, draft_id),
            )
        self.log(actor, "draft", "promote", f"D#{draft_id} -> P#{plan_id}")
        return replace(
            self._row_to_draft(row),
            status="promoted",
            plan_id=plan_id,
            promoted_at=stamp,
            updated_at=stamp,
        )

    def delete_draft(self, draft_id: int, actor: str = "human") -> bool:
        """Delete one draft; revisions and annotations cascade."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM plan_drafts WHERE id=?", (draft_id,))
            removed = (cur.rowcount or 0) > 0
        if removed:
            self.log(actor, "draft", "delete", f"D#{draft_id}")
        return removed
