"""Store methods for views."""

from __future__ import annotations

from ..kinds import KIND_ERROR, table_for
from ..models import (
    ForgeLink,
    Milestone,
    Plan,
    Status,
    Task,
    VcsLink,
)
from .base import StoreBase, to_payload


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
        return {
            "task": self._task_view(t),
            "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
            "links": [vars(c) for c in self.list_links("task", t.id)],
            "effective_links": [vars(c) for c in self.effective_links("task", t.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("task", t.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("task", t.id)],
            "repos": self.list_repos("task", t.id),
            "effective_repos": self.effective_repos("task", t.id),
        }

    def _milestone_show(self, s: Milestone) -> dict:
        """Milestone show payload with task summaries."""
        payload = {
            "milestone": to_payload(vars(s)),
            "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
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
                    "criteria": [vars(c) for c in self.list_criteria("task", t.id)],
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
        payload = {
            "plan": to_payload(vars(p)),
            "criteria": [vars(c) for c in self.list_criteria("plan", p.id)],
            "links": [vars(c) for c in self.list_links("plan", p.id)],
            "effective_links": [vars(c) for c in self.effective_links("plan", p.id)],
            "forge_links": [vars(c) for c in self.list_forge_links("plan", p.id)],
            "effective_forge_links": [vars(c) for c in self.effective_forge_links("plan", p.id)],
            "repos": self.list_repos("plan", p.id),
            "effective_repos": self.effective_repos("plan", p.id),
            "milestones": [
                {
                    "milestone": to_payload(vars(s)),
                    "criteria": [vars(c) for c in self.list_criteria("milestone", s.id)],
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
                    plan.id: plan for plan in self.list_plans()
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

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]:
        """Latest 'plan #id -> status' event per plan, keyed by plan id."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ts, detail FROM events WHERE kind='plan' AND action='status'"
                " ORDER BY id DESC"
            ).fetchall()
        out: dict[int, tuple[float, str]] = {}
        for row in rows:
            detail = str(row["detail"] or "").removesuffix(" (rollup)")
            if not detail.startswith("plan #"):
                continue
            body = detail[len("plan #") :]
            try:
                plan_text, target = body.split(" -> ", 1)
                plan_id = int(plan_text)
            except ValueError:
                continue
            out.setdefault(plan_id, (float(row["ts"]), target))
        return out

    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool:
        """Raw status write, no healing or logging (see services)."""
        table = table_for(kind)
        with self._connect() as conn:
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


class _FullReader:
    """Build full show payloads from one set of bulk maps."""

    def __init__(self, store: StoreBase) -> None:
        self.milestones = store.milestones_map()
        self.tasks = store.tasks_map()
        self.criteria = store.criteria_map()
        self.links = store.vcs_links_map()
        self.forge = store.forge_links_map()
        self.repos = store.repos_map()
        self.claims = store.claims_map()
        self.notes = store.notes_full_map()
        self.comments = store.comments_full_map()
        self.issues = store.issue_links_map()
        self.milestone_by_id = {
            milestone.id: milestone for items in self.milestones.values() for milestone in items
        }
        self.task_by_id = {task.id: task for items in self.tasks.values() for task in items}

    def _gate_state(self, task_id: int) -> dict:
        links = self.forge.get(("task", task_id), [])
        if not links:
            return {"prs": 0, "checks": "none", "state": "missing"}
        values = [str(link.checks or "none") for link in links]
        if any(value == "fail" for value in values):
            checks = "fail"
        elif any(value == "pending" for value in values):
            checks = "pending"
        elif all(value in {"pass", "neutral", "skipped"} for value in values):
            checks = "pass"
        else:
            checks = "none"
        return {
            "prs": len(links),
            "checks": checks,
            "state": "pass" if checks == "pass" else checks,
        }

    def _task_view(self, task: Task) -> dict:
        data = to_payload(vars(task))
        claim = self.claims.get(task.id)
        if claim is not None:
            data["claim"] = vars(claim)
        notes = self.notes.get(("task", task.id), [])
        if notes:
            data["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("task", task.id), [])
        if comments:
            data["comments"] = [vars(comment) for comment in comments]
        gate = self._gate_state(task.id)
        if gate["prs"]:
            data["gate"] = gate
        issue_refs = self.issues.get(("task", task.id), [])
        if issue_refs:
            data["issues"] = issue_refs
        return data

    def _effective_links(self, kind: str, obj_id: int) -> list[VcsLink]:
        links = list(self.links.get((kind, obj_id), []))
        if kind == "milestone":
            for task in self.tasks.get(obj_id, ()):
                links.extend(self.links.get(("task", task.id), []))
        elif kind == "plan":
            for milestone in self.milestones.get(obj_id, ()):
                links.extend(self.links.get(("milestone", milestone.id), []))
                for task in self.tasks.get(milestone.id, ()):
                    links.extend(self.links.get(("task", task.id), []))
        seen: set[tuple[str, str]] = set()
        out: list[VcsLink] = []
        for link in links:
            key = (link.sha, link.repo_root)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def _effective_forge(self, kind: str, obj_id: int) -> list[ForgeLink]:
        links = list(self.forge.get((kind, obj_id), []))
        if kind == "milestone":
            for task in self.tasks.get(obj_id, ()):
                links.extend(self.forge.get(("task", task.id), []))
        elif kind == "plan":
            for milestone in self.milestones.get(obj_id, ()):
                links.extend(self.forge.get(("milestone", milestone.id), []))
                for task in self.tasks.get(milestone.id, ()):
                    links.extend(self.forge.get(("task", task.id), []))
        seen: set[tuple[str, str, int]] = set()
        out: list[ForgeLink] = []
        for link in links:
            key = (link.provider, link.kind, link.number)
            if key in seen:
                continue
            seen.add(key)
            out.append(link)
        return out

    def _effective_repos(self, kind: str, obj_id: int) -> list[dict]:
        explicit = self.repos.get((kind, obj_id), [])
        if explicit:
            return explicit
        if kind == "task":
            task = self.task_by_id.get(obj_id)
            if task is not None:
                return self._effective_repos("milestone", task.milestone_id)
        elif kind == "milestone":
            milestone = self.milestone_by_id.get(obj_id)
            if milestone is not None:
                return self.repos.get(("plan", milestone.plan_id), [])
        return []

    def task(self, task: Task) -> dict:
        return {
            "task": self._task_view(task),
            "criteria": [vars(item) for item in self.criteria.get(("task", task.id), [])],
            "links": [vars(item) for item in self.links.get(("task", task.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("task", task.id)],
            "forge_links": [vars(item) for item in self.forge.get(("task", task.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("task", task.id)
            ],
            "repos": self.repos.get(("task", task.id), []),
            "effective_repos": self._effective_repos("task", task.id),
        }

    def milestone(self, milestone: Milestone) -> dict:
        payload = {
            "milestone": to_payload(vars(milestone)),
            "criteria": [vars(item) for item in self.criteria.get(("milestone", milestone.id), [])],
            "links": [vars(item) for item in self.links.get(("milestone", milestone.id), [])],
            "effective_links": [
                vars(item) for item in self._effective_links("milestone", milestone.id)
            ],
            "forge_links": [vars(item) for item in self.forge.get(("milestone", milestone.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("milestone", milestone.id)
            ],
            "repos": self.repos.get(("milestone", milestone.id), []),
            "effective_repos": self._effective_repos("milestone", milestone.id),
            "tasks": [
                {
                    "task": self._task_view(task),
                    "criteria": [vars(item) for item in self.criteria.get(("task", task.id), [])],
                }
                for task in self.tasks.get(milestone.id, ())
            ],
        }
        notes = self.notes.get(("milestone", milestone.id), [])
        if notes:
            payload["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("milestone", milestone.id), [])
        if comments:
            payload["comments"] = [vars(comment) for comment in comments]
        issue_refs = self.issues.get(("milestone", milestone.id), [])
        if issue_refs:
            payload["issues"] = issue_refs
        return payload

    def plan(self, plan: Plan) -> dict:
        payload = {
            "plan": to_payload(vars(plan)),
            "criteria": [vars(item) for item in self.criteria.get(("plan", plan.id), [])],
            "links": [vars(item) for item in self.links.get(("plan", plan.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("plan", plan.id)],
            "forge_links": [vars(item) for item in self.forge.get(("plan", plan.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("plan", plan.id)
            ],
            "repos": self.repos.get(("plan", plan.id), []),
            "effective_repos": self._effective_repos("plan", plan.id),
            "milestones": [
                {
                    "milestone": to_payload(vars(milestone)),
                    "criteria": [
                        vars(item) for item in self.criteria.get(("milestone", milestone.id), [])
                    ],
                    "repos": self.repos.get(("milestone", milestone.id), []),
                    "effective_repos": self._effective_repos("milestone", milestone.id),
                    "tasks": [self._task_view(task) for task in self.tasks.get(milestone.id, ())],
                }
                for milestone in self.milestones.get(plan.id, ())
            ],
        }
        notes = self.notes.get(("plan", plan.id), [])
        if notes:
            payload["notes"] = [vars(note) for note in notes]
        comments = self.comments.get(("plan", plan.id), [])
        if comments:
            payload["comments"] = [vars(comment) for comment in comments]
        issue_refs = self.issues.get(("plan", plan.id), [])
        if issue_refs:
            payload["issues"] = issue_refs
        return payload
