"""Approval snapshots and scope drift.

A snapshot is the canonical scope tree for one plan: the plan title, why, and
what; each milestone title and description; each task title and description;
and every criterion text. Status, claims, ticks, commits, pull requests, notes,
comments, and trace links are deliberately absent: they are execution or proof,
not scope.

The digest is a sha256 over canonical JSON, so equal scope always produces an
equal digest. The diff is pure and compares two snapshots without reading the
database.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..entities import Criterion, Milestone, Plan, Task

#: Bumped when the snapshot shape changes in a way that invalidates old digests.
SNAPSHOT_SCHEMA = 1

_PLAN_FIELDS = ("title", "why", "what")
_ROW_FIELDS = {"milestone": ("title", "desc"), "task": ("title", "desc")}
_KIND_ORDER = {"plan": 0, "milestone": 1, "task": 2, "criterion": 3}


@dataclass(frozen=True)
class Change:
    """One scope difference between two snapshots."""

    kind: str  # plan | milestone | task | criterion
    action: str  # add | remove | change | move
    obj_id: int
    identity: str
    title: str
    field: str = ""
    before: str = ""
    after: str = ""
    parent: str = ""

    def sort_key(self) -> tuple[int, int, str, str]:
        """Stable order: kind, row id, identity, field."""
        return (_KIND_ORDER.get(self.kind, 99), self.obj_id, self.identity, self.field)


def _identity(kind: str, payload: Mapping[str, Any]) -> str:
    """Stable key when present, else kind:id."""
    key = str(payload.get("key") or "")
    return key or f"{kind}:{payload.get('id', 0)}"


def _criteria_payload(
    criteria: Mapping[tuple[str, int], Sequence[Criterion]],
    kind: str,
    obj_id: int,
) -> list[dict[str, Any]]:
    """Criteria on one row, ordered by id, scope text only."""
    items = sorted(criteria.get((kind, obj_id), ()), key=lambda item: item.id)
    return [{"id": item.id, "text": item.text} for item in items]


def build_snapshot(
    plan: Plan,
    milestones: Sequence[Milestone],
    tasks: Mapping[int, Sequence[Task]],
    criteria: Mapping[tuple[str, int], Sequence[Criterion]],
    keys: Mapping[tuple[str, int], str],
) -> dict[str, Any]:
    """Build the canonical scope tree for *plan* from preloaded rows."""
    plan_key = keys.get(("plan", plan.id), "")

    def key(kind: str, obj_id: int) -> str:
        return keys.get((kind, obj_id), "")

    plan_payload = {
        "id": plan.id,
        "key": plan_key,
        "title": plan.name,
        "why": plan.goal,
        "what": plan.description,
        "criteria": _criteria_payload(criteria, "plan", plan.id),
    }
    milestone_payloads: list[dict[str, Any]] = []
    for milestone in sorted(milestones, key=lambda item: item.id):
        milestone_payloads.append(
            {
                "id": milestone.id,
                "key": key("milestone", milestone.id),
                "title": milestone.title,
                "desc": milestone.description,
                "criteria": _criteria_payload(criteria, "milestone", milestone.id),
                "tasks": [
                    {
                        "id": task.id,
                        "key": key("task", task.id),
                        "title": task.title,
                        "desc": task.description,
                        "criteria": _criteria_payload(criteria, "task", task.id),
                    }
                    for task in sorted(tasks.get(milestone.id, ()), key=lambda item: item.id)
                ],
            }
        )
    return {"schema": SNAPSHOT_SCHEMA, "plan": plan_payload, "milestones": milestone_payloads}


def canonical(snapshot: Mapping[str, Any]) -> str:
    """Canonical JSON text: sorted keys, no extra whitespace."""
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(snapshot: Mapping[str, Any]) -> str:
    """sha256 of the canonical JSON."""
    return hashlib.sha256(canonical(snapshot).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _Entry:
    """One indexed row and the identity of its parent."""

    payload: Mapping[str, Any]
    parent: str


def _index(
    snapshot: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    str,
    dict[str, _Entry],
    dict[str, _Entry],
    dict[str, _Entry],
]:
    """Index one snapshot by identity at each level."""
    plan = snapshot.get("plan") or {}
    plan_identity = _identity("plan", plan)
    milestones: dict[str, _Entry] = {}
    tasks: dict[str, _Entry] = {}
    criteria: dict[str, _Entry] = {}

    for milestone in snapshot.get("milestones") or []:
        milestone_identity = _identity("milestone", milestone)
        milestones[milestone_identity] = _Entry(milestone, plan_identity)
        for criterion in milestone.get("criteria") or []:
            identity = _identity("criterion", criterion)
            criteria[identity] = _Entry(criterion, milestone_identity)
        for task in milestone.get("tasks") or []:
            task_identity = _identity("task", task)
            tasks[task_identity] = _Entry(task, milestone_identity)
            for criterion in task.get("criteria") or []:
                identity = _identity("criterion", criterion)
                criteria[identity] = _Entry(criterion, task_identity)

    for criterion in plan.get("criteria") or []:
        identity = _identity("criterion", criterion)
        criteria[identity] = _Entry(criterion, plan_identity)

    return plan, plan_identity, milestones, tasks, criteria


def _title(kind: str, payload: Mapping[str, Any]) -> str:
    """Display title for one row: name, title, or criterion text."""
    if kind == "plan":
        return str(payload.get("title") or payload.get("name") or "")
    if kind == "criterion":
        return str(payload.get("text") or "")
    return str(payload.get("title") or "")


def _change(
    kind: str,
    action: str,
    entry: _Entry,
    *,
    field: str = "",
    before: str = "",
    after: str = "",
) -> Change:
    payload = entry.payload
    return Change(
        kind=kind,
        action=action,
        obj_id=int(payload.get("id", 0) or 0),
        identity=_identity(kind, payload),
        title=_title(kind, payload),
        field=field,
        before=before,
        after=after,
        parent=entry.parent,
    )


def _compare(
    kind: str,
    before: _Entry,
    after: _Entry,
    changes: list[Change],
) -> None:
    """Append change and move entries for one matched row."""
    if before.parent != after.parent:
        changes.append(
            _change(
                kind,
                "move",
                after,
                field="parent",
                before=before.parent,
                after=after.parent,
            )
        )
    fields = _PLAN_FIELDS if kind == "plan" else _ROW_FIELDS.get(kind, ("text",))
    for field in fields:
        old = str(before.payload.get(field, "") or "")
        new = str(after.payload.get(field, "") or "")
        if old != new:
            changes.append(_change(kind, "change", after, field=field, before=old, after=new))


def diff_snapshots(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> tuple[Change, ...]:
    """Compare two snapshots and return scope changes in stable order.

    A removed milestone is one entry, not one per descendant task and
    criterion. The same rule applies to a removed task. Additions follow the
    same shape, so a new milestone does not repeat every task it contains.
    """
    before_plan, _, before_milestones, before_tasks, before_criteria = _index(before)
    after_plan, _, after_milestones, after_tasks, after_criteria = _index(after)
    changes: list[Change] = []

    for field in _PLAN_FIELDS:
        old = str(before_plan.get(field, "") or "")
        new = str(after_plan.get(field, "") or "")
        if old != new:
            entry = _Entry(after_plan, "")
            changes.append(_change("plan", "change", entry, field=field, before=old, after=new))

    added_milestones = set(after_milestones) - set(before_milestones)
    removed_milestones = set(before_milestones) - set(after_milestones)
    for identity in sorted(added_milestones):
        changes.append(_change("milestone", "add", after_milestones[identity]))
    for identity in sorted(removed_milestones):
        changes.append(_change("milestone", "remove", before_milestones[identity]))
    for identity in sorted(set(before_milestones) & set(after_milestones)):
        _compare(
            "milestone",
            before_milestones[identity],
            after_milestones[identity],
            changes,
        )

    added_tasks = set(after_tasks) - set(before_tasks)
    removed_tasks = set(before_tasks) - set(after_tasks)
    for identity in sorted(added_tasks):
        entry = after_tasks[identity]
        if entry.parent not in added_milestones:
            changes.append(_change("task", "add", entry))
    for identity in sorted(removed_tasks):
        entry = before_tasks[identity]
        if entry.parent not in removed_milestones:
            changes.append(_change("task", "remove", entry))
    for identity in sorted(set(before_tasks) & set(after_tasks)):
        _compare("task", before_tasks[identity], after_tasks[identity], changes)

    added_criteria = set(after_criteria) - set(before_criteria)
    removed_criteria = set(before_criteria) - set(after_criteria)
    hidden_parents = added_milestones | removed_milestones | added_tasks | removed_tasks
    for identity in sorted(added_criteria):
        entry = after_criteria[identity]
        if entry.parent not in hidden_parents:
            changes.append(_change("criterion", "add", entry))
    for identity in sorted(removed_criteria):
        entry = before_criteria[identity]
        if entry.parent not in hidden_parents:
            changes.append(_change("criterion", "remove", entry))
    for identity in sorted(set(before_criteria) & set(after_criteria)):
        _compare("criterion", before_criteria[identity], after_criteria[identity], changes)

    return tuple(sorted(changes, key=Change.sort_key))


def summarize(changes: Sequence[Change]) -> dict[str, int]:
    """Count changes by action plus a total."""
    summary = {"add": 0, "remove": 0, "change": 0, "move": 0}
    for change in changes:
        summary[change.action] += 1
    summary["total"] = len(changes)
    return summary
