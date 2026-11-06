"""Plan approval and drift use cases.

The service builds the canonical scope snapshot from the store, compares it
with the latest approved revision, and attaches the reason recorded for each
scope change. It is read-only except for the explicit approve action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..core.entities import PlanChange, PlanRevision
from ..core.policies.revisions import (
    Change,
    build_snapshot,
    canonical,
    diff_snapshots,
    digest,
    summarize,
)
from ..core.ports.revisions import RevisionsPort


@dataclass(frozen=True)
class ApprovalResult:
    """One approval attempt: the stored revision and what changed."""

    revision: PlanRevision
    created: bool
    acknowledged: int


@dataclass(frozen=True)
class RevisionEntry:
    """A stored revision and the changes it acknowledged."""

    revision: PlanRevision
    changes: int


@dataclass(frozen=True)
class DiffEntry:
    """One scope change with the reason recorded for it."""

    change: Change
    reason: str = ""
    actor: str = ""
    ts: float = 0.0
    change_id: int = 0


@dataclass(frozen=True)
class DiffResult:
    """The drift report between one stored revision and a target."""

    plan_id: int
    from_revision: PlanRevision
    to_revision: PlanRevision | None
    entries: tuple[DiffEntry, ...]
    summary: dict[str, int]

    @property
    def drifted(self) -> bool:
        """True when the target differs from the baseline."""
        return bool(self.entries)


def snapshot(port: RevisionsPort, plan_id: int) -> dict:
    """Build the canonical live scope snapshot for one plan."""
    plan = port.get_plan(plan_id)
    if plan is None:
        raise KeyError(f"plan #{plan_id} not found")
    return build_snapshot(
        plan,
        port.list_milestones(plan_id),
        port.tasks_map(),
        port.criteria_map(),
        port.entity_keys_map(),
    )


def _load(revision: PlanRevision) -> dict:
    """Decode one stored snapshot, naming the revision on failure."""
    try:
        value = json.loads(revision.snapshot)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"revision r{revision.revision} snapshot is not valid JSON: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"revision r{revision.revision} snapshot is not an object")
    return value


def _find(revisions: list[PlanRevision], number: int) -> PlanRevision:
    """Find one revision by number or raise a clear error."""
    for revision in revisions:
        if revision.revision == number:
            return revision
    raise ValueError(f"no revision r{number} for this plan")


def _acknowledged(port: RevisionsPort, plan_id: int, revision: PlanRevision) -> int:
    """Changes between the previous revision and this one."""
    previous = next(
        (
            item
            for item in reversed(port.list_revisions(plan_id))
            if item.revision < revision.revision
        ),
        None,
    )
    mark = previous.change_mark if previous is not None else 0
    return sum(
        1
        for change in port.list_plan_changes(plan_id, after_id=mark)
        if change.id <= revision.change_mark
    )


def approve(
    port: RevisionsPort,
    plan_id: int,
    actor: str = "human",
    reason: str = "",
    enforced: bool = False,
) -> ApprovalResult:
    """Approve the live scope, or acknowledge a policy-only change.

    An identical snapshot with the same enforcement is a no-op. A different
    snapshot needs a reason. A changed enforcement on an identical snapshot is
    a policy revision: it creates a new row without requiring a reason.
    """
    with port.transaction():
        latest = port.latest_revision(plan_id)
        live = snapshot(port, plan_id)
        live_digest = digest(live)
        if latest is not None and latest.digest == live_digest and latest.enforced == enforced:
            return ApprovalResult(latest, False, 0)
        if latest is not None and latest.digest != live_digest and not reason.strip():
            raise ValueError("re-approval with drift needs a reason")
        revision = port.add_revision(
            plan_id,
            live_digest,
            canonical(live),
            reason=reason.strip(),
            change_mark=port.max_change_id(plan_id),
            enforced=enforced,
            actor=actor,
        )
        return ApprovalResult(revision, True, _acknowledged(port, plan_id, revision))


def list_revisions(port: RevisionsPort, plan_id: int) -> list[RevisionEntry]:
    """Approval history, oldest first, with acknowledged change counts."""
    items = port.list_revisions(plan_id)
    entries: list[RevisionEntry] = []
    previous_mark = 0
    for revision in items:
        count = sum(
            1
            for change in port.list_plan_changes(plan_id, after_id=previous_mark)
            if change.id <= revision.change_mark
        )
        entries.append(RevisionEntry(revision, count))
        previous_mark = revision.change_mark
    return entries


def _reason(
    change: Change,
    changes: list[PlanChange],
) -> DiffEntry:
    """Attach the latest matching recorded change to one diff entry."""
    action = {"add": "add", "remove": "delete", "change": "edit", "move": "edit"}.get(
        change.action, ""
    )
    field = change.field if change.action in ("change", "move") else ""
    matches = [
        item
        for item in changes
        if item.kind == change.kind
        and item.obj_id == change.obj_id
        and item.action == action
        and (not field or item.field == field)
    ]
    if not matches:
        return DiffEntry(change)
    latest = matches[-1]
    return DiffEntry(change, latest.reason, latest.actor, latest.ts, latest.id)


def diff(
    port: RevisionsPort,
    plan_id: int,
    from_revision: int | None = None,
    to_revision: int | None = None,
) -> DiffResult:
    """Compare one stored revision with live scope or another revision."""
    items = port.list_revisions(plan_id)
    if not items:
        raise ValueError(f"plan #{plan_id} has no approved revision; run plan approve")
    before = items[-1] if from_revision is None else _find(items, from_revision)
    if to_revision is None:
        after_snapshot = snapshot(port, plan_id)
        after = None
        changes = port.list_plan_changes(plan_id, after_id=before.change_mark)
    else:
        after = _find(items, to_revision)
        after_snapshot = _load(after)
        changes = []
    entries = tuple(
        _reason(change, changes) for change in diff_snapshots(_load(before), after_snapshot)
    )
    return DiffResult(
        plan_id=plan_id,
        from_revision=before,
        to_revision=after,
        entries=entries,
        summary=summarize([entry.change for entry in entries]),
    )


def drifted_plan_ids(port: RevisionsPort) -> set[int]:
    """Plans with scope changes after their latest approval."""
    return set(port.drift_counts())


def drift_counts(port: RevisionsPort) -> dict[int, int]:
    """Scope changes after the latest approval, per plan."""
    return port.drift_counts()


def revision_state(port: RevisionsPort, plan_id: int) -> dict:
    """Latest revision, enforcement, and live drift for one plan."""
    latest = port.latest_revision(plan_id)
    if latest is None:
        return {"revision": 0, "enforced": False, "drift": 0}
    return {
        "revision": latest.revision,
        "enforced": latest.enforced,
        "drift": port.plan_drift(plan_id),
    }
