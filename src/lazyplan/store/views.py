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
from ..core.serialization import approval_payload
from .base import StoreBase, to_payload
from .full_reader import _criterion_payload, _FullReader
from .status_events import parse_plan_status_detail


def _release_lease_for_status(
    conn: sqlite3.Connection, kind: str, obj_id: int, status: Status
) -> None:
    """A task that is no longer doing cannot keep a lease."""
    if kind == "task" and status is not Status.DOING:
        conn.execute("DELETE FROM task_claims WHERE task_id=?", (obj_id,))


def _leading_int(text: str, start: int) -> int | None:
    """Positive integer immediately after *start*, else None."""
    end = start
    while end < len(text) and text[end].isdigit():
        end += 1
    return int(text[start:end]) if end > start else None


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
        return _leading_int(detail, 2)
    if detail.startswith("plan #"):
        return _leading_int(detail, 6)
    if detail.startswith("M#"):
        return _plan_for_milestone(_leading_int(detail, 2), milestone_plan)
    if detail.startswith("milestone #"):
        return _plan_for_milestone(_leading_int(detail, 11), milestone_plan)
    if detail.startswith("T#"):
        return _plan_for_task(_leading_int(detail, 2), task_milestone, milestone_plan)
    if detail.startswith("task #"):
        return _plan_for_task(_leading_int(detail, 6), task_milestone, milestone_plan)
    if detail.startswith("criteria #"):
        return _plan_for_criterion(
            _leading_int(detail, 10), criterion_parent, task_milestone, milestone_plan
        )
    if detail.startswith("criterion #"):
        return _plan_for_criterion(
            _leading_int(detail, 11), criterion_parent, task_milestone, milestone_plan
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

    def _task_view(self, t: Task) -> dict:
        """Task fields plus any active or expired claim."""
        data = to_payload(vars(t))
        claim = self.get_claim(t.id)
        if claim is not None:
            data["claim"] = vars(claim)
        notes = self.list_notes("task", t.id)
        if notes:
            data["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("task", t.id)
        if comments:
            data["comments"] = [vars(c) for c in comments]
        gate = self.gate_state(t.id)
        if gate["prs"]:
            data["gate"] = gate
        issue_refs = self.list_issue_links("task", t.id)
        if issue_refs:
            data["issues"] = issue_refs
        return data

    def _task_show(self, t: Task) -> dict:
        """Task show payload with direct links and inherited repos."""
        evidence = self.evidence_map()
        return {
            "task": self._task_view(t),
            "criteria": [_criterion_payload(c, evidence) for c in self.list_criteria("task", t.id)],
            "links": [vars(c) for c in self.list_links("task", t.id)],
            "effective_links": [vars(c) for c in self.effective_links("task", t.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("task", t.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("task", t.id)],
            "repos": self.list_repos("task", t.id),
            "effective_repos": self.effective_repos("task", t.id),
            "touchpoints": self.list_touchpoints(t.id),
        }

    def _milestone_show(self, s: Milestone) -> dict:
        """Milestone show payload with task summaries."""
        evidence = self.evidence_map()
        payload = {
            "milestone": to_payload(vars(s)),
            "criteria": [
                _criterion_payload(c, evidence) for c in self.list_criteria("milestone", s.id)
            ],
            "links": [vars(c) for c in self.list_links("milestone", s.id)],
            "effective_links": [vars(c) for c in self.effective_links("milestone", s.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("milestone", s.id)],
            "effective_forge_links": [
                vars(c) for c in self.effective_forge_links("milestone", s.id)
            ],
            "repos": self.list_repos("milestone", s.id),
            "effective_repos": self.effective_repos("milestone", s.id),
            "tasks": [
                {
                    "task": self._task_view(t),
                    "criteria": [
                        _criterion_payload(c, evidence) for c in self.list_criteria("task", t.id)
                    ],
                }
                for t in self.list_tasks(s.id)
            ],
        }
        notes = self.list_notes("milestone", s.id)
        if notes:
            payload["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("milestone", s.id)
        if comments:
            payload["comments"] = [vars(c) for c in comments]
        issue_refs = self.list_issue_links("milestone", s.id)
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def _plan_show(self, p: Plan) -> dict:
        """Plan show payload with milestone summaries."""
        latest = self.latest_revision(p.id)
        recent = self.list_plan_changes(p.id, after_id=latest.change_mark)[-3:] if latest else []
        evidence = self.evidence_map()
        payload = {
            "plan": to_payload(vars(p)),
            "criteria": [_criterion_payload(c, evidence) for c in self.list_criteria("plan", p.id)],
            "links": [vars(c) for c in self.list_links("plan", p.id)],
            "effective_links": [vars(c) for c in self.effective_links("plan", p.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("plan", p.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("plan", p.id)],
            "repos": self.list_repos("plan", p.id),
            "effective_repos": self.effective_repos("plan", p.id),
            "approval": approval_payload(latest, self.plan_drift(p.id), recent),
            "questions": [vars(q) for q in self.list_questions(p.id, status="all")],
            "refs": [vars(ref) for ref in self.list_refs(p.id)],
            "milestones": [
                {
                    "milestone": to_payload(vars(s)),
                    "criteria": [
                        _criterion_payload(c, evidence)
                        for c in self.list_criteria("milestone", s.id)
                    ],
                    "repos": self.list_repos("milestone", s.id),
                    "effective_repos": self.effective_repos("milestone", s.id),
                    "tasks": [self._task_view(t) for t in self.list_tasks(s.id)],
                }
                for s in self.list_milestones(p.id)
            ],
        }
        notes = self.list_notes("plan", p.id)
        if notes:
            payload["notes"] = [vars(n) for n in notes]
        comments = self.list_comments("plan", p.id)
        if comments:
            payload["comments"] = [vars(c) for c in comments]
        issue_refs = self.list_issue_links("plan", p.id)
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        """Full context record for `lpui show`: fields + criteria + links + repos + children."""
        with self._connect():
            if kind == "plan":
                p = self.get_plan(obj_id)
                return None if p is None else self._plan_show(p)
            if kind == "milestone":
                s = self.get_milestone(obj_id)
                return None if s is None else self._milestone_show(s)
            if kind == "task":
                t = self.get_task(obj_id)
                return None if t is None else self._task_show(t)
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
