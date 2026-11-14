"""Store methods for views."""

from __future__ import annotations

import sqlite3

from ..core.entities import (
    Milestone,
    Plan,
    Status,
    Task,
)
from ..core.kinds import KIND_ERROR, table_for
from ..core.policies.insights import leading_int
from .base import StoreBase
from .full_reader import _FullReader
from .status_events import parse_plan_status_detail


def _release_lease_for_status(
    conn: sqlite3.Connection, kind: str, obj_id: int, status: Status
) -> None:
    """A task that is no longer doing cannot keep a lease."""
    if kind == "task" and status is not Status.DOING:
        conn.execute("DELETE FROM task_claims WHERE task_id=?", (obj_id,))


def _plan_for_milestone(mid: int | None, milestone_plan: dict[int, int]) -> int | None:
    return milestone_plan.get(mid) if mid is not None else None


def _plan_for_task(
    tid: int | None,
    task_milestone: dict[int, int],
    milestone_plan: dict[int, int],
) -> int | None:
    if tid is None:
        return None
    return _plan_for_milestone(task_milestone.get(tid), milestone_plan)


def _plan_for_criterion(
    cid: int | None,
    criterion_parent: dict[int, tuple[str, int]],
    task_milestone: dict[int, int],
    milestone_plan: dict[int, int],
) -> int | None:
    if cid is None:
        return None
    found = criterion_parent.get(cid)
    if found is None:
        return None
    kind, parent_id = found
    if kind == "plan":
        return parent_id
    if kind == "milestone":
        return _plan_for_milestone(parent_id, milestone_plan)
    return _plan_for_task(parent_id, task_milestone, milestone_plan)


def _detail_plan_id(
    detail: str,
    milestone_plan: dict[int, int],
    task_milestone: dict[int, int],
    criterion_parent: dict[int, tuple[str, int]],
) -> int | None:
    """Owning plan encoded in one event detail, or None."""
    if detail.startswith("P#"):
        return leading_int(detail, 2)
    if detail.startswith("plan #"):
        return leading_int(detail, 6)
    if detail.startswith("M#"):
        return _plan_for_milestone(leading_int(detail, 2), milestone_plan)
    if detail.startswith("milestone #"):
        return _plan_for_milestone(leading_int(detail, 11), milestone_plan)
    if detail.startswith("T#"):
        return _plan_for_task(leading_int(detail, 2), task_milestone, milestone_plan)
    if detail.startswith("task #"):
        return _plan_for_task(leading_int(detail, 6), task_milestone, milestone_plan)
    if detail.startswith("criteria #"):
        return _plan_for_criterion(
            leading_int(detail, 10), criterion_parent, task_milestone, milestone_plan
        )
    if detail.startswith("criterion #"):
        return _plan_for_criterion(
            leading_int(detail, 11), criterion_parent, task_milestone, milestone_plan
        )
    return None


class ViewsMixin(StoreBase):
    """Views persistence."""

    def get_parent(self, kind: str, obj_id: int) -> Plan | Milestone | Task | None:
        """Fetch any row by kind (criteria parent lookup)."""
        if kind == "plan":
            return self.get_plan(obj_id)
        if kind == "milestone":
            return self.get_milestone(obj_id)
        if kind == "task":
            return self.get_task(obj_id)
        raise ValueError(KIND_ERROR)

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lpui show`: fields + criteria + links + repos + children."""
        with self._connect():
            if kind == "plan":
                p = self.get_plan(obj_id)
                if p is None:
                    return None
                latest = self.latest_revision(obj_id)
                recent = (
                    self.list_plan_changes(obj_id, after_id=latest.change_mark)[-3:]
                    if latest
                    else []
                )
                return _FullReader(self).plan(p, recent=recent)
            if kind == "milestone":
                s = self.get_milestone(obj_id)
                return None if s is None else _FullReader(self).milestone(s)
            if kind == "task":
                t = self.get_task(obj_id)
                return None if t is None else _FullReader(self).task(t)
        raise ValueError(KIND_ERROR)

    def get_full_many(self, kind: str, obj_ids: list[int]) -> list[dict]:
        """Full context records for several rows, in the requested order."""
        with self._connect():
            reader = _FullReader(self)
            if kind == "plan":
                objects: dict[int, Plan | Milestone | Task] = {
                    plan.id: plan for plan in self.list_plans(archived="show")
                }
            elif kind == "milestone":
                objects = {
                    milestone.id: milestone
                    for items in reader.milestones.values()
                    for milestone in items
                }
            elif kind == "task":
                objects = {task.id: task for items in reader.tasks.values() for task in items}
            else:
                raise ValueError(KIND_ERROR)
            out: list[dict] = []
            for obj_id in obj_ids:
                obj = objects.get(obj_id)
                if obj is None:
                    continue
                if isinstance(obj, Plan):
                    out.append(reader.plan(obj))
                elif isinstance(obj, Milestone):
                    out.append(reader.milestone(obj))
                else:
                    out.append(reader.task(obj))
            return out

    def status_events(self, kind: str) -> list[tuple[float, str]]:
        """(ts, detail) status moves for a kind, newest first (archive policy input)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind=? AND action='status' ORDER BY id DESC",
                (kind,),
            ).fetchall()
        return [(r["ts"], r["detail"]) for r in rows]

    def plan_activity_map(self, limit_events: int = 100_000) -> dict[int, float]:
        """Latest event timestamp per plan from one bounded, prefix-parsed read.

        The event table is the largest read path in the tree. This keeps the
        scan bounded and parses the structured prefixes with slicing instead of
        compiling a regex per row.
        """
        events = self.feed(limit=max(1, int(limit_events)))
        if not events:
            return {}
        milestone_plan = {
            milestone.id: plan_id
            for plan_id, milestones in self.milestones_map().items()
            for milestone in milestones
        }
        task_milestone = {
            task.id: milestone_id
            for milestone_id, tasks in self.tasks_map().items()
            for task in tasks
        }
        criterion_parent = {
            criterion.id: (criterion.parent_kind, criterion.parent_id)
            for items in self.criteria_map().values()
            for criterion in items
        }
        out: dict[int, float] = {}
        for event in events:
            detail = str(event.get("detail") or "")
            plan_id = _detail_plan_id(detail, milestone_plan, task_milestone, criterion_parent)
            if plan_id is None:
                continue
            stamp = float(event.get("ts") or 0.0)
            if stamp > out.get(plan_id, 0.0):
                out[plan_id] = stamp
        return out

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]:
        """Latest 'plan #id -> status' event per plan, keyed by plan id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind='plan' AND action='status'"
                " ORDER BY id DESC"
            ).fetchall()
        out: dict[int, tuple[float, str]] = {}
        for row in rows:
            parsed = parse_plan_status_detail(str(row["detail"] or ""))
            if parsed is None:
                continue
            plan_id, target = parsed
            out.setdefault(plan_id, (float(row["ts"]), target))
        return out

    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool:
        """Raw status write, no healing; a task leaving doing loses its lease."""
        table = table_for(kind)
        with self._connect() as conn:
            _release_lease_for_status(conn, kind, obj_id, status)
            cur = conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status.value, obj_id))
            return (cur.rowcount or 0) > 0

    def counts(self) -> dict[str, int]:
        """Plan, milestone, and task totals, plus per-state plan counts."""
        with self._connect() as conn:
            np = conn.execute("SELECT COUNT(*) c FROM plans").fetchone()["c"]
            ns = conn.execute("SELECT COUNT(*) c FROM milestones").fetchone()["c"]
            nt = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
            nd = conn.execute("SELECT COUNT(*) c FROM tasks WHERE status='done'").fetchone()["c"]
            npt = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='todo'").fetchone()["c"]
            npd = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='doing'").fetchone()["c"]
            npn = conn.execute("SELECT COUNT(*) c FROM plans WHERE status='done'").fetchone()["c"]
        return {
            "plans": np,
            "milestones": ns,
            "tasks": nt,
            "tasks_done": nd,
            "plans_todo": npt,
            "plans_doing": npd,
            "plans_done": npn,
        }
