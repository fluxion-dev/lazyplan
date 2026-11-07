"""Review packet: one deterministic Markdown handoff for a plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.entities import Criterion, Task
from ..core.policies.evidence import proof_state
from ..core.policies.review import render
from ..core.ports.insights import InsightsPort
from . import audit, lint, ready


@dataclass(frozen=True)
class ReviewPacket:
    """One rendered packet and the structured payload behind it."""

    plan_id: int
    markdown: str
    payload: dict


def _criterion(store: InsightsPort, criterion: Criterion, tasks: list[Task]) -> dict:
    """One criterion row with proving tasks, provenance, and evidence."""
    commits = []
    prs = []
    for task in tasks:
        commits.extend(store.effective_links("task", task.id))
        prs.extend(store.effective_forge_links("task", task.id))
    return {
        "id": criterion.id,
        "kind": criterion.parent_kind,
        "parent": criterion.parent_id,
        "text": criterion.text,
        "done": criterion.done,
        "tasks": [{"id": task.id, "title": task.title} for task in tasks],
        "commits": [
            {"sha": link.sha, "subject": link.subject, "repo": link.repo_root} for link in commits
        ],
        "prs": [
            {
                "number": link.number,
                "title": link.title,
                "url": link.url,
                "state": link.state,
            }
            for link in prs
        ],
        "evidence": proof_state(store.list_evidence(criterion.id)),
    }


def _criteria(store: InsightsPort, plan_id: int) -> list[dict]:
    """Every plan, milestone, and task criterion in the tree."""
    out = [
        _criterion(store, criterion, store.criterion_tasks(criterion.id))
        for criterion in store.list_criteria("plan", plan_id)
    ]
    for milestone in store.list_milestones(plan_id):
        out.extend(
            _criterion(store, criterion, store.criterion_tasks(criterion.id))
            for criterion in store.list_criteria("milestone", milestone.id)
        )
        for task in store.list_tasks(milestone.id):
            out.extend(
                _criterion(store, criterion, store.criterion_tasks(criterion.id))
                for criterion in store.list_criteria("task", task.id)
            )
    return out


def _milestones(store: InsightsPort, plan_id: int) -> list[dict]:
    """Milestones with their tasks, in creation order."""
    return [
        {
            "id": milestone.id,
            "title": milestone.title,
            "status": milestone.status.value,
            "tasks": [
                {"id": task.id, "title": task.title, "status": task.status.value}
                for task in store.list_tasks(milestone.id)
            ],
        }
        for milestone in store.list_milestones(plan_id)
    ]


def _readiness(store: InsightsPort, plan_id: int) -> dict:
    """Readiness checks in JSON-safe shape."""
    result = ready.check(store, plan_id)
    if result is None:
        return {"ready": False, "checks": []}
    return {
        "ready": result.ready,
        "checks": [
            {
                "id": check.id,
                "ok": check.ok,
                "detail": check.detail,
                "findings": list(check.findings),
            }
            for check in result.checks
        ],
    }


def build(
    store: InsightsPort,
    plan_id: int,
    max_chars: int = 0,
    cwd: str | Path = ".",
) -> ReviewPacket | None:
    """Compose one review packet; None when the plan does not exist."""
    plan = store.get_plan(plan_id)
    if plan is None:
        return None
    full = store.get_full("plan", plan_id)
    if full is None:
        return None
    report = audit.report(store, [plan_id], cwd=cwd)
    payload = {
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "status": plan.status.value,
        },
        "approval": full.get("approval"),
        "readiness": _readiness(store, plan_id),
        "why": plan.goal,
        "what": plan.description,
        "criteria": _criteria(store, plan_id),
        "milestones": _milestones(store, plan_id),
        "commits": [
            {"sha": link.sha, "subject": link.subject, "repo": link.repo_root}
            for link in store.effective_links("plan", plan_id)
        ],
        "prs": [
            {
                "number": link.number,
                "title": link.title,
                "url": link.url,
                "state": link.state,
            }
            for link in store.effective_forge_links("plan", plan_id)
        ],
        "lint": [finding.to_dict() for finding in lint.lint_plan(store, plan_id) or []],
        "audit": report.to_dict(),
        "questions": [vars(question) for question in store.list_questions(plan_id)],
        "notes": [vars(note) for note in store.list_notes("plan", plan_id)[-3:]],
    }
    return ReviewPacket(plan_id, render(payload, max_chars), payload)
