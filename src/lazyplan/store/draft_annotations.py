"""Store methods for anchored draft annotations."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace

from ..core.entities import DraftAnnotation
from ..core.kinds import DRAFT_ANNOTATION_STATUSES
from .base import StoreBase


class DraftAnnotationsMixin(StoreBase):
    """Anchored feedback on a draft revision."""

    @staticmethod
    def _row_to_draft_annotation(r: sqlite3.Row) -> DraftAnnotation:
        """Row to DraftAnnotation."""
        return DraftAnnotation(
            id=int(r["id"]),
            draft_id=int(r["draft_id"]),
            block_key=str(r["block_key"]),
            quote=str(r["quote"]),
            start_offset=int(r["start_offset"]),
            end_offset=int(r["end_offset"]),
            kind=str(r["kind"]),
            body=str(r["body"]),
            status=str(r["status"]),
            author=str(r["author"]),
            ts=float(r["ts"]),
            revision=int(r["revision"]),
            response=str(r["response"]),
            responded_by=str(r["responded_by"]),
            responded_at=float(r["responded_at"]),
            anchor_state=str(r["anchor_state"]),
        )

    def add_draft_annotation(
        self,
        draft_id: int,
        block_key: str,
        kind: str,
        body: str,
        *,
        quote: str = "",
        start_offset: int = 0,
        end_offset: int = 0,
        revision: int | None = None,
        author: str = "human",
        now: float | None = None,
    ) -> DraftAnnotation:
        """Append one annotation to a draft revision."""
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            row = conn.execute(
                "SELECT revision FROM plan_drafts WHERE id=?", (draft_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"draft #{draft_id} not found")
            current = int(row["revision"])
            if revision is None:
                revision = current
            if revision != current:
                raise ValueError(f"draft #{draft_id} is at revision {current}, not {revision}")
            annotation = DraftAnnotation(
                id=0,
                draft_id=draft_id,
                block_key=block_key.strip(),
                kind=kind,
                body=body.strip(),
                author=author,
                ts=stamp,
                revision=revision,
                quote=quote,
                start_offset=start_offset,
                end_offset=end_offset,
            )
            cur = conn.execute(
                "INSERT INTO draft_annotations"
                " (draft_id, block_key, quote, start_offset, end_offset, kind, body,"
                " status, author, ts, revision, response, responded_by, responded_at,"
                " anchor_state)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    annotation.draft_id,
                    annotation.block_key,
                    annotation.quote,
                    annotation.start_offset,
                    annotation.end_offset,
                    annotation.kind,
                    annotation.body,
                    annotation.status,
                    annotation.author,
                    annotation.ts,
                    annotation.revision,
                    annotation.response,
                    annotation.responded_by,
                    annotation.responded_at,
                    annotation.anchor_state,
                ),
            )
            annotation_id = int(cur.lastrowid or 0)
        self.log(author, "draft", "annotate", f"D#{draft_id} A#{annotation_id} {kind}")
        return replace(annotation, id=annotation_id)

    def get_draft_annotation(self, annotation_id: int) -> DraftAnnotation | None:
        """Fetch one draft annotation by id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM draft_annotations WHERE id=?", (annotation_id,)
            ).fetchone()
        return self._row_to_draft_annotation(row) if row is not None else None

    def list_draft_annotations(self, draft_id: int, status: str = "all") -> list[DraftAnnotation]:
        """Annotations for one draft, oldest first, optionally by status."""
        if status != "all" and status not in DRAFT_ANNOTATION_STATUSES:
            raise ValueError(f"annotation status must be all|{'|'.join(DRAFT_ANNOTATION_STATUSES)}")
        with self._connect() as conn:
            if status == "all":
                rows = conn.execute(
                    "SELECT * FROM draft_annotations WHERE draft_id=? ORDER BY id",
                    (draft_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM draft_annotations WHERE draft_id=? AND status=? ORDER BY id",
                    (draft_id, status),
                ).fetchall()
        return [self._row_to_draft_annotation(row) for row in rows]

    def update_draft_annotation(
        self,
        annotation_id: int,
        actor: str = "human",
        *,
        status: str | None = None,
        response: str | None = None,
        responded_by: str | None = None,
        responded_at: float | None = None,
        anchor_state: str | None = None,
        start_offset: int | None = None,
        end_offset: int | None = None,
    ) -> DraftAnnotation | None:
        """Update one annotation's state, response, or anchor."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM draft_annotations WHERE id=?", (annotation_id,)
            ).fetchone()
            if row is None:
                return None
            updated = DraftAnnotation(
                id=int(row["id"]),
                draft_id=int(row["draft_id"]),
                block_key=str(row["block_key"]),
                quote=str(row["quote"]),
                start_offset=int(row["start_offset"]) if start_offset is None else start_offset,
                end_offset=int(row["end_offset"]) if end_offset is None else end_offset,
                kind=str(row["kind"]),
                body=str(row["body"]),
                status=str(row["status"]) if status is None else status,
                author=str(row["author"]),
                ts=float(row["ts"]),
                revision=int(row["revision"]),
                response=str(row["response"]) if response is None else response,
                responded_by=str(row["responded_by"]) if responded_by is None else responded_by,
                responded_at=float(row["responded_at"]) if responded_at is None else responded_at,
                anchor_state=str(row["anchor_state"]) if anchor_state is None else anchor_state,
            )
            conn.execute(
                "UPDATE draft_annotations"
                " SET status=?, response=?, responded_by=?, responded_at=?,"
                " anchor_state=?, start_offset=?, end_offset=?"
                " WHERE id=?",
                (
                    updated.status,
                    updated.response,
                    updated.responded_by,
                    updated.responded_at,
                    updated.anchor_state,
                    updated.start_offset,
                    updated.end_offset,
                    annotation_id,
                ),
            )
        action = "annotation-edit"
        if status is not None:
            action = status
        elif anchor_state is not None:
            action = "reanchor"
        self.log(actor, "draft", action, f"A#{annotation_id}")
        return updated

    def delete_draft_annotation(self, annotation_id: int, actor: str = "human") -> bool:
        """Delete one annotation."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM draft_annotations WHERE id=?", (annotation_id,))
            removed = (cur.rowcount or 0) > 0
        if removed:
            self.log(actor, "draft", "annotation-delete", f"A#{annotation_id}")
        return removed

    def draft_annotation_counts(self, draft_id: int) -> tuple[int, int]:
        """Open and total annotation counts for one draft."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total,"
                " COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS open"
                " FROM draft_annotations WHERE draft_id=?",
                (draft_id,),
            ).fetchone()
        return int(row["open"]), int(row["total"])

    def draft_annotation_counts_map(self) -> dict[int, tuple[int, int]]:
        """Open and total annotation counts per draft, in one query."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT draft_id, COUNT(*) AS total,"
                " COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS open"
                " FROM draft_annotations GROUP BY draft_id ORDER BY draft_id"
            ).fetchall()
        return {int(row["draft_id"]): (int(row["open"]), int(row["total"])) for row in rows}
