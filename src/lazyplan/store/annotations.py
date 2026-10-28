"""Store methods for annotations."""

from __future__ import annotations

import sqlite3
import time

from ..kinds import check_parent_kind
from ..models import (
    Comment,
    Criterion,
    Note,
    Task,
)
from .base import (
    StoreBase,
)


class AnnotationsMixin(StoreBase):
    """Annotations persistence."""

    @staticmethod
    def _row_to_note(r: sqlite3.Row) -> Note:
        """Row to Note."""
        return Note(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
        )

    def add_note(self, parent_kind: str, parent_id: int, text: str, actor: str = "human") -> Note:
        """Append a handoff note and log it."""
        check_parent_kind(parent_kind)
        body = text.strip()
        if not body:
            raise ValueError("note text must not be empty")
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, stamp, body),
            )
            note_id = cur.lastrowid or 0
        self.log(actor, parent_kind, "note", f"{parent_kind} #{parent_id}: {body[:80]}")
        return Note(
            id=note_id,
            parent_kind=parent_kind,
            parent_id=parent_id,
            text=body,
            actor=actor,
            ts=stamp,
        )

    def list_notes(self, parent_kind: str, parent_id: int, limit: int | None = None) -> list[Note]:
        """Notes on one row, oldest first; limit keeps the latest N."""
        check_parent_kind(parent_kind)
        sql = "SELECT * FROM notes WHERE parent_kind=? AND parent_id=? ORDER BY id DESC"
        params: list[object] = [parent_kind, parent_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(max(int(limit), 1))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_note(row) for row in reversed(rows)]

    def restore_note(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
    ) -> Note | None:
        """Import a note with its original timestamp."""
        if not text.strip():
            return None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, ts, text.strip()),
            )
            note_id = cur.lastrowid or 0
        return Note(note_id, parent_kind, parent_id, text.strip(), actor, ts)

    def add_issue_link(
        self,
        provider: str,
        external_id: str,
        number: str,
        url: str,
        title: str,
        state: str,
        row_kind: str,
        row_id: int,
        updated_at: float = 0,
    ) -> dict:
        """Record one imported issue source."""
        check_parent_kind(row_kind)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO issue_links"
                " (provider, external_id, number, url, title, state, row_kind, row_id, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (provider, external_id, number, url, title, state, row_kind, row_id, updated_at),
            )
            link_id = cur.lastrowid or 0
        return {
            "id": link_id,
            "provider": provider,
            "external_id": external_id,
            "number": number,
            "url": url,
            "title": title,
            "state": state,
            "row_kind": row_kind,
            "row_id": row_id,
            "updated_at": updated_at,
        }

    def get_issue_link(self, provider: str, external_id: str) -> dict | None:
        """Find a source link by provider and external id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM issue_links WHERE provider=? AND external_id=?",
                (provider, external_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_issue_links(self, row_kind: str, row_id: int) -> list[dict]:
        """Issue sources attached to one row."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM issue_links WHERE row_kind=? AND row_id=? ORDER BY id",
                (row_kind, row_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def issue_links_map(self) -> dict[tuple[str, int], list[dict]]:
        """Every issue source grouped by (row_kind, row_id), oldest first."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM issue_links ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[dict]] = {}
        for row in rows:
            item = dict(row)
            out.setdefault((str(item["row_kind"]), int(item["row_id"])), []).append(item)
        return out

    def update_issue_link(
        self, provider: str, external_id: str, title: str, url: str, state: str, updated_at: float
    ) -> bool:
        """Refresh cached source metadata without touching the row."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE issue_links SET title=?, url=?, state=?, updated_at=?"
                " WHERE provider=? AND external_id=?",
                (title, url, state, updated_at, provider, external_id),
            )
            return (cur.rowcount or 0) > 0

    @staticmethod
    def _row_to_comment(r: sqlite3.Row) -> Comment:
        """Row to Comment."""
        return Comment(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            actor=str(r["actor"]),
            ts=float(r["ts"]),
            resolved=bool(r["resolved"]),
        )

    def add_comment(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Comment:
        """Append a review comment and log it."""
        check_parent_kind(parent_kind)
        body = text.strip()
        if not body:
            raise ValueError("comment text must not be empty")
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text) VALUES (?,?,?,?,?)",
                (parent_kind, parent_id, actor, stamp, body),
            )
            comment_id = cur.lastrowid or 0
        self.log(actor, parent_kind, "comment", f"{parent_kind} #{parent_id}: {body[:80]}")
        return Comment(comment_id, parent_kind, parent_id, body, actor, stamp, False)

    def list_comments(
        self, parent_kind: str, parent_id: int, mentions: str | None = None
    ) -> list[Comment]:
        """Comments on one row, oldest first; optionally only @name mentions."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM comments WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        items = [self._row_to_comment(row) for row in rows]
        if mentions:
            needle = f"@{mentions.lstrip('@').lower()}"
            items = [item for item in items if needle in item.text.lower()]
        return items

    def resolve_comment(
        self, cid: int, resolved: bool = True, actor: str = "human"
    ) -> Comment | None:
        """Set or clear a comment's resolved flag."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM comments WHERE id=?", (cid,)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE comments SET resolved=? WHERE id=?", (1 if resolved else 0, cid))
        self.log(actor, "comment", "resolve" if resolved else "unresolve", f"comment #{cid}")
        comment = self._row_to_comment(row)
        return Comment(
            comment.id,
            comment.parent_kind,
            comment.parent_id,
            comment.text,
            comment.actor,
            comment.ts,
            resolved,
        )

    def restore_comment(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str,
        ts: float,
        resolved: bool,
    ) -> Comment | None:
        """Import a comment with its timestamp and resolution state."""
        if not text.strip():
            return None
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO comments (parent_kind, parent_id, actor, ts, text, resolved)"
                " VALUES (?,?,?,?,?,?)",
                (parent_kind, parent_id, actor, ts, text.strip(), 1 if resolved else 0),
            )
            comment_id = cur.lastrowid or 0
        return Comment(comment_id, parent_kind, parent_id, text.strip(), actor, ts, resolved)

    def notes_map(self) -> dict[tuple[str, int], list[str]]:
        """All note text grouped by parent, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute("SELECT parent_kind, parent_id, text FROM notes").fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["parent_kind"]), int(row["parent_id"])), []).append(
                str(row["text"])
            )
        return out

    def comments_map(self) -> dict[tuple[str, int], list[str]]:
        """All comment text grouped by parent, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute("SELECT parent_kind, parent_id, text FROM comments").fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["parent_kind"]), int(row["parent_id"])), []).append(
                str(row["text"])
            )
        return out

    def notes_full_map(self) -> dict[tuple[str, int], list[Note]]:
        """Every note grouped by parent, oldest first, with full metadata."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM notes ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Note]] = {}
        for row in rows:
            note = self._row_to_note(row)
            out.setdefault((note.parent_kind, note.parent_id), []).append(note)
        return out

    def comments_full_map(self) -> dict[tuple[str, int], list[Comment]]:
        """Every comment grouped by parent, oldest first, with full metadata."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM comments ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Comment]] = {}
        for row in rows:
            comment = self._row_to_comment(row)
            out.setdefault((comment.parent_kind, comment.parent_id), []).append(comment)
        return out

    def issues_map(self) -> dict[tuple[str, int], list[str]]:
        """Issue source text grouped by row, for TUI search."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT row_kind, row_id, provider, number, title, url FROM issue_links"
            ).fetchall()
        out: dict[tuple[str, int], list[str]] = {}
        for row in rows:
            out.setdefault((str(row["row_kind"]), int(row["row_id"])), []).append(
                " ".join(str(row[key]) for key in ("provider", "number", "title", "url"))
            )
        return out

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

    @staticmethod
    def _row_to_criterion(r: sqlite3.Row) -> Criterion:
        """Row to Criterion."""
        return Criterion(
            id=int(r["id"]),
            parent_kind=str(r["parent_kind"]),
            parent_id=int(r["parent_id"]),
            text=str(r["text"]),
            done=bool(r["done"]),
        )

    def get_criterion(self, cid: int) -> Criterion | None:
        """Fetch one checklist item by id."""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM criteria WHERE id=?", (cid,)).fetchone()
        return self._row_to_criterion(r) if r is not None else None

    def relate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        """Record that a task proves a criterion."""
        if self.get_criterion(criterion_id) is None:
            raise KeyError(f"criterion #{criterion_id} not found")
        if self.get_task(task_id) is None:
            raise KeyError(f"task #{task_id} not found")
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO criterion_links (criterion_id, task_id) VALUES (?,?)",
                (criterion_id, task_id),
            )
            inserted = (cur.rowcount or 0) > 0
        if not inserted:
            raise ValueError(f"criterion #{criterion_id} is already linked to task #{task_id}")
        self.log(
            actor,
            "criterion",
            "relate",
            f"criterion #{criterion_id} <- task #{task_id}",
        )
        return True

    def unrelate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        """Remove a criterion-task proof relation."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM criterion_links WHERE criterion_id=? AND task_id=?",
                (criterion_id, task_id),
            )
            removed = (cur.rowcount or 0) > 0
        if removed:
            self.log(
                actor,
                "criterion",
                "unrelate",
                f"criterion #{criterion_id} -/-> task #{task_id}",
            )
        return removed

    def criterion_tasks(self, criterion_id: int) -> list[Task]:
        """Tasks that prove one criterion, in task id order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT t.* FROM tasks t"
                " JOIN criterion_links l ON l.task_id=t.id"
                " WHERE l.criterion_id=? ORDER BY t.id",
                (criterion_id,),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def task_criteria(self, task_id: int) -> list[Criterion]:
        """Criteria proved by one task, in criterion id order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.* FROM criteria c"
                " JOIN criterion_links l ON l.criterion_id=c.id"
                " WHERE l.task_id=? ORDER BY c.id",
                (task_id,),
            ).fetchall()
        return [self._row_to_criterion(r) for r in rows]

    def all_criterion_links(self) -> list[dict]:
        """Every criterion-task relation, for export."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT criterion_id, task_id FROM criterion_links ORDER BY criterion_id, task_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]:
        """Checklist items of a plan, milestone, or task."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM criteria WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [self._row_to_criterion(r) for r in rows]

    def criteria_map(self) -> dict[tuple[str, int], list[Criterion]]:
        """Every checklist item grouped by (parent_kind, parent_id), in id order."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM criteria ORDER BY id").fetchall()
        out: dict[tuple[str, int], list[Criterion]] = {}
        for row in rows:
            criterion = self._row_to_criterion(row)
            out.setdefault((criterion.parent_kind, criterion.parent_id), []).append(criterion)
        return out

    def open_task_criteria_ids(self) -> set[int]:
        """Task ids that still have at least one open criterion."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT parent_id FROM criteria"
                " WHERE parent_kind='task' AND done=0 ORDER BY parent_id"
            ).fetchall()
        return {int(row["parent_id"]) for row in rows}

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
