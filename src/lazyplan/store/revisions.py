"""Store methods for plan approvals and recorded scope changes."""

from __future__ import annotations

import sqlite3
import time

from ..core.entities import PlanChange, PlanRevision
from ..core.kinds import SCOPE_KINDS
from .base import StoreBase


class RevisionsMixin(StoreBase):
    """Approval snapshots and the scope-change ledger."""

    @staticmethod
    def _row_to_revision(r: sqlite3.Row) -> PlanRevision:
        """Row to PlanRevision."""
        return PlanRevision(
            id=int(r["id"]),
            plan_id=int(r["plan_id"]),
            revision=int(r["revision"]),
            approved_at=float(r["approved_at"]),
            actor=str(r["actor"]),
            reason=str(r["reason"]),
            digest=str(r["digest"]),
            snapshot=str(r["snapshot"]),
            change_mark=int(r["change_mark"]),
            enforced=bool(r["enforced"]),
        )

    @staticmethod
    def _row_to_change(r: sqlite3.Row) -> PlanChange:
        """Row to PlanChange."""
        return PlanChange(
            id=int(r["id"]),
            plan_id=int(r["plan_id"]),
            ts=float(r["ts"]),
            actor=str(r["actor"]),
            kind=str(r["kind"]),
            obj_id=int(r["obj_id"]),
            action=str(r["action"]),
            field=str(r["field"]),
            reason=str(r["reason"]),
            detail=str(r["detail"]),
        )

    def add_revision(
        self,
        plan_id: int,
        digest: str,
        snapshot: str,
        reason: str = "",
        change_mark: int = 0,
        enforced: bool = False,
        actor: str = "human",
    ) -> PlanRevision:
        """Append the next approval revision for one plan."""
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM plans WHERE id=?", (plan_id,)).fetchone() is None:
                raise KeyError(f"plan #{plan_id} not found")
            revision = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM plan_revisions WHERE plan_id=?",
                (plan_id,),
            ).fetchone()[0]
            stamp = time.time()
            cur = conn.execute(
                "INSERT INTO plan_revisions"
                " (plan_id, revision, approved_at, actor, reason, digest, snapshot,"
                " change_mark, enforced)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    plan_id,
                    revision,
                    stamp,
                    actor,
                    reason,
                    digest,
                    snapshot,
                    change_mark,
                    1 if enforced else 0,
                ),
            )
            revision_id = cur.lastrowid or 0
        self.log(actor, "plan", "approve", f"P#{plan_id} r{revision} {reason[:80]}".strip())
        return PlanRevision(
            id=revision_id,
            plan_id=plan_id,
            revision=int(revision),
            approved_at=stamp,
            actor=actor,
            reason=reason,
            digest=digest,
            snapshot=snapshot,
            change_mark=change_mark,
            enforced=enforced,
        )

    def latest_revision(self, plan_id: int) -> PlanRevision | None:
        """Newest approval for one plan, or None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plan_revisions WHERE plan_id=? ORDER BY revision DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
        return self._row_to_revision(row) if row is not None else None

    def latest_revisions_map(self) -> dict[int, PlanRevision]:
        """Latest approval per plan, in one query."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM plan_revisions r"
                " JOIN (SELECT plan_id, MAX(revision) AS revision"
                "       FROM plan_revisions GROUP BY plan_id) latest"
                "   ON latest.plan_id=r.plan_id AND latest.revision=r.revision"
            ).fetchall()
        return {int(row["plan_id"]): self._row_to_revision(row) for row in rows}

    def list_revisions(self, plan_id: int) -> list[PlanRevision]:
        """Every approval for one plan, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plan_revisions WHERE plan_id=? ORDER BY revision",
                (plan_id,),
            ).fetchall()
        return [self._row_to_revision(row) for row in rows]

    def add_plan_change(
        self,
        plan_id: int,
        kind: str,
        obj_id: int,
        action: str,
        field: str = "",
        reason: str = "",
        detail: str = "",
        actor: str = "human",
    ) -> PlanChange:
        """Append one scope-changing edit to the plan ledger."""
        if kind not in SCOPE_KINDS:
            raise ValueError(f"kind must be {'|'.join(SCOPE_KINDS)}")
        if action not in ("add", "edit", "delete"):
            raise ValueError("action must be add|edit|delete")
        stamp = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO plan_changes"
                " (plan_id, ts, actor, kind, obj_id, action, field, reason, detail)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (plan_id, stamp, actor, kind, obj_id, action, field, reason, detail),
            )
            change_id = cur.lastrowid or 0
        return PlanChange(
            id=change_id,
            plan_id=plan_id,
            ts=stamp,
            actor=actor,
            kind=kind,
            obj_id=obj_id,
            action=action,
            field=field,
            reason=reason,
            detail=detail,
        )

    def list_plan_changes(self, plan_id: int, after_id: int = 0) -> list[PlanChange]:
        """Scope changes for one plan after a change mark, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plan_changes WHERE plan_id=? AND id>? ORDER BY id",
                (plan_id, after_id),
            ).fetchall()
        return [self._row_to_change(row) for row in rows]

    def max_change_id(self, plan_id: int) -> int:
        """Newest recorded change id for one plan, or 0."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM plan_changes WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
        return int(row[0])

    def drift_counts(self) -> dict[int, int]:
        """Changes after the latest revision, per plan, in one query."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.plan_id, COUNT(*) AS changes"
                " FROM plan_changes c"
                " JOIN plan_revisions r ON r.plan_id=c.plan_id"
                " JOIN (SELECT plan_id, MAX(revision) AS revision"
                "       FROM plan_revisions GROUP BY plan_id) latest"
                "   ON latest.plan_id=r.plan_id AND latest.revision=r.revision"
                " WHERE c.id > r.change_mark"
                " GROUP BY c.plan_id"
            ).fetchall()
        return {int(row["plan_id"]): int(row["changes"]) for row in rows}

    def plan_drift(self, plan_id: int) -> int:
        """Changes after the latest revision for one plan."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS changes"
                " FROM plan_changes c"
                " JOIN plan_revisions r ON r.plan_id=c.plan_id"
                " WHERE c.plan_id=? AND c.id > r.change_mark"
                "   AND r.revision=(SELECT MAX(revision) FROM plan_revisions WHERE plan_id=?)",
                (plan_id, plan_id),
            ).fetchone()
        return int(row["changes"]) if row is not None else 0

    def _plan_for_kind(self, kind: str, obj_id: int) -> int | None:
        """Resolve the owning plan id for a plan, milestone, task, or criterion."""
        if kind not in SCOPE_KINDS:
            return None
        with self._connect() as conn:
            if kind == "plan":
                row = conn.execute("SELECT id FROM plans WHERE id=?", (obj_id,)).fetchone()
                return int(row["id"]) if row is not None else None
            if kind == "milestone":
                row = conn.execute(
                    "SELECT plan_id FROM milestones WHERE id=?", (obj_id,)
                ).fetchone()
                return int(row["plan_id"]) if row is not None else None
            if kind == "task":
                row = conn.execute(
                    "SELECT m.plan_id FROM tasks t JOIN milestones m ON m.id=t.milestone_id"
                    " WHERE t.id=?",
                    (obj_id,),
                ).fetchone()
                return int(row["plan_id"]) if row is not None else None
            row = conn.execute(
                "SELECT parent_kind, parent_id FROM criteria WHERE id=?", (obj_id,)
            ).fetchone()
        if row is None:
            return None
        return self._plan_for_kind(str(row["parent_kind"]), int(row["parent_id"]))

    def _record_scope_change(
        self,
        plan_id: int,
        kind: str,
        obj_id: int,
        action: str,
        field: str = "",
        reason: str = "",
        detail: str = "",
        actor: str = "human",
    ) -> PlanChange | None:
        """Record one change only when the plan already has an approval."""
        if self.latest_revision(plan_id) is None:
            return None
        return self.add_plan_change(
            plan_id,
            kind,
            obj_id,
            action,
            field=field,
            reason=reason,
            detail=detail,
            actor=actor,
        )

    def _record_scope_change_for(
        self,
        kind: str,
        obj_id: int,
        action: str,
        field: str = "",
        reason: str = "",
        detail: str = "",
        actor: str = "human",
    ) -> PlanChange | None:
        """Resolve the owning plan, then record one scope change."""
        plan_id = self._plan_for_kind(kind, obj_id)
        if plan_id is None:
            return None
        return self._record_scope_change(
            plan_id,
            kind,
            obj_id,
            action,
            field=field,
            reason=reason,
            detail=detail,
            actor=actor,
        )
