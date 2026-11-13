"""Full show payloads built from one set of bulk maps."""

from __future__ import annotations

from ..core.entities import Criterion, CriterionEvidence, ForgeLink, Milestone, Plan, Task, VcsLink
from ..core.policies.evidence import summarize as evidence_summary
from ..core.serialization import approval_payload, to_payload
from .base import StoreBase


def _criterion_payload(criterion: Criterion, evidence: dict[int, list[CriterionEvidence]]) -> dict:
    """Criterion fields plus its evidence count, state, and latest row."""
    summary = evidence_summary(evidence.get(criterion.id, ()))
    latest = summary["latest"]
    data = vars(criterion).copy()
    data["evidence"] = {
        "count": summary["count"],
        "state": summary["state"],
        "latest": vars(latest) if latest is not None else None,
    }
    return data


class _FullReader:
    """Build full show payloads from one set of bulk maps."""

    def __init__(self, store: StoreBase) -> None:
        self._store = store
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
        self.revisions = store.latest_revisions_map()
        self.drift = store.drift_counts()
        self.evidence = store.evidence_map()
        self.questions = store.questions_map()
        self.touchpoints = store.touchpoints_map()
        self.refs = store.refs_map()
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

    def _criteria(self, kind: str, obj_id: int) -> list[dict]:
        """Criteria on one row with evidence summaries."""
        return [
            _criterion_payload(item, self.evidence)
            for item in self.criteria.get((kind, obj_id), [])
        ]

    def task(self, task: Task) -> dict:
        return {
            "task": self._task_view(task),
            "criteria": self._criteria("task", task.id),
            "links": [vars(item) for item in self.links.get(("task", task.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("task", task.id)],
            "forge_links": [vars(item) for item in self.forge.get(("task", task.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("task", task.id)
            ],
            "repos": self.repos.get(("task", task.id), []),
            "effective_repos": self._effective_repos("task", task.id),
            "touchpoints": self.touchpoints.get(task.id, []),
        }

    def milestone(self, milestone: Milestone) -> dict:
        payload = {
            "milestone": to_payload(vars(milestone)),
            "criteria": self._criteria("milestone", milestone.id),
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
                    "criteria": self._criteria("task", task.id),
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
            "criteria": self._criteria("plan", plan.id),
            "links": [vars(item) for item in self.links.get(("plan", plan.id), [])],
            "effective_links": [vars(item) for item in self._effective_links("plan", plan.id)],
            "forge_links": [vars(item) for item in self.forge.get(("plan", plan.id), [])],
            "effective_forge_links": [
                vars(item) for item in self._effective_forge("plan", plan.id)
            ],
            "repos": self.repos.get(("plan", plan.id), []),
            "effective_repos": self._effective_repos("plan", plan.id),
            "worktrees": [vars(row) for row in self._store.list_plan_worktrees(plan.id)],
            "approval": approval_payload(self.revisions.get(plan.id), self.drift.get(plan.id, 0)),
            "questions": [vars(q) for q in self.questions.get(plan.id, [])],
            "refs": [vars(ref) for ref in self.refs.get(plan.id, [])],
            "milestones": [
                {
                    "milestone": to_payload(vars(milestone)),
                    "criteria": self._criteria("milestone", milestone.id),
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
