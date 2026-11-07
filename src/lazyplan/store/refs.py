"""Store methods for external plan references."""

from __future__ import annotations

import sqlite3
import time

from ..core.entities import ExternalRef
from ..core.policies.refs import normalize_ref
from .base import StoreBase


class RefsMixin(StoreBase):
    """Read-only links from a plan to an external epic, issue, or doc."""

    @staticmethod
    def _row_to_ref(r: sqlite3.Row) -> ExternalRef:
        """Row to ExternalRef."""
        return ExternalRef(
            id=int(r["id"]),
            plan_id=int(r["plan_id"]),
            url=str(r["url"]),
            provider=str(r["provider"]),
            kind=str(r["kind"]),
            external_id=str(r["external_id"] or ""),
            title=str(r["title"] or ""),
            state=str(r["state"] or ""),
            actor=str(r["actor"] or "human"),
            created_at=float(r["created_at"] or 0),
        )

    def link_ref(
        self,
        plan_id: int,
        url: str,
        provider: str = "",
        kind: str = "issue",
        external_id: str = "",
        title: str = "",
        state: str = "",
        actor: str = "human",
        now: float | None = None,
    ) -> ExternalRef:
        """Link one external URL to a plan; a repeat updates the snapshot fields."""
        fields = normalize_ref(url, provider, kind, external_id)
        stamp = time.time() if now is None else now
        with self._connect() as conn:
            plan = conn.execute("SELECT id FROM plans WHERE id=?", (plan_id,)).fetchone()
            if plan is None:
                raise KeyError(f"plan #{plan_id} not found")
            conn.execute(
                "INSERT INTO external_refs"
                " (plan_id, provider, kind, external_id, url, title, state, actor, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(plan_id, url) DO UPDATE SET"
                " provider=excluded.provider, kind=excluded.kind,"
                " external_id=excluded.external_id, title=excluded.title,"
                " state=excluded.state",
                (
                    plan_id,
                    fields["provider"],
                    fields["kind"],
                    fields["external_id"],
                    fields["url"],
                    title.strip(),
                    state.strip(),
                    actor,
                    stamp,
                ),
            )
            row = conn.execute(
                "SELECT * FROM external_refs WHERE plan_id=? AND url=?",
                (plan_id, fields["url"]),
            ).fetchone()
        assert row is not None
        ref = self._row_to_ref(row)
        self.log(actor, "plan", "ref-link", f"P#{plan_id} {ref.url}")
        return ref

    def list_refs(self, plan_id: int) -> list[ExternalRef]:
        """References on one plan, in creation order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM external_refs WHERE plan_id=? ORDER BY id", (plan_id,)
            ).fetchall()
        return [self._row_to_ref(row) for row in rows]

    def refs_map(self) -> dict[int, list[ExternalRef]]:
        """Every reference grouped by plan id."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM external_refs ORDER BY id").fetchall()
        out: dict[int, list[ExternalRef]] = {}
        for row in rows:
            ref = self._row_to_ref(row)
            out.setdefault(ref.plan_id, []).append(ref)
        return out

    def unlink_ref(
        self,
        plan_id: int,
        ref_id: int = 0,
        url: str = "",
        actor: str = "human",
    ) -> bool:
        """Remove a reference by row id or URL."""
        if not ref_id and not url:
            raise ValueError("unlink a reference by id or url")
        with self._connect() as conn:
            if ref_id:
                cur = conn.execute(
                    "DELETE FROM external_refs WHERE plan_id=? AND id=?", (plan_id, ref_id)
                )
            else:
                cur = conn.execute(
                    "DELETE FROM external_refs WHERE plan_id=? AND url=?", (plan_id, url.strip())
                )
        if cur.rowcount:
            self.log(actor, "plan", "ref-unlink", f"P#{plan_id} {ref_id or url}")
            return True
        return False
