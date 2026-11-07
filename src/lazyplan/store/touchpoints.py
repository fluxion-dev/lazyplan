"""Store methods for task touch-points."""

from __future__ import annotations

from ..core.policies.coordination import normalize_touchpoint
from .base import StoreBase


class TouchpointsMixin(StoreBase):
    """Explicit repo-relative paths a task expects to edit."""

    def add_touchpoint(self, task_id: int, pattern: str, actor: str = "human") -> str:
        """Add one normalized touch-point; a repeat is a no-op."""
        clean = normalize_touchpoint(pattern)
        with self._connect() as conn:
            task = conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise KeyError(f"task #{task_id} not found")
            cur = conn.execute(
                "INSERT OR IGNORE INTO task_touchpoints (task_id, pattern) VALUES (?,?)",
                (task_id, clean),
            )
        if cur.rowcount:
            self.log(actor, "task", "touch", f"T#{task_id}: {clean}")
        return clean

    def remove_touchpoint(self, task_id: int, pattern: str, actor: str = "human") -> bool:
        """Remove one touch-point; True when a row was deleted."""
        clean = normalize_touchpoint(pattern)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM task_touchpoints WHERE task_id=? AND pattern=?", (task_id, clean)
            )
        if cur.rowcount:
            self.log(actor, "task", "untouch", f"T#{task_id}: {clean}")
            return True
        return False

    def list_touchpoints(self, task_id: int) -> list[str]:
        """Patterns on one task, sorted."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT pattern FROM task_touchpoints WHERE task_id=? ORDER BY pattern", (task_id,)
            ).fetchall()
        return [str(row["pattern"]) for row in rows]

    def touchpoints_map(self) -> dict[int, list[str]]:
        """Every task's patterns, grouped by task id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id, pattern FROM task_touchpoints ORDER BY task_id, pattern"
            ).fetchall()
        out: dict[int, list[str]] = {}
        for row in rows:
            out.setdefault(int(row["task_id"]), []).append(str(row["pattern"]))
        return out
