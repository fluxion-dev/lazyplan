"""CLI rendering for approvals, revision history, and drift."""

from __future__ import annotations

import time
from typing import Any

from ...core.entities import Plan
from ...services.revisions import ApprovalResult, DiffResult, RevisionEntry
from ..shared import porcelain


def _date(stamp: float) -> str:
    """Stored timestamp as a stable local date."""
    return time.strftime("%Y-%m-%d", time.localtime(stamp))


def _short(text: str, limit: int = 60) -> str:
    """One-line excerpt for a diff field."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _reason(entry: Any) -> str:
    """Reason suffix for one diff entry."""
    return f"reason: {entry.reason}" if entry.reason else "no reason"


def _revision_payload(revision: Any) -> dict:
    """Revision fields without the bulky snapshot text."""
    data = dict(vars(revision))
    data.pop("snapshot", None)
    return data


def _label(entry: Any) -> str:
    """Short kind and id for one diff entry."""
    change = entry.change
    labels = {"plan": f"P{change.obj_id}", "milestone": f"M{change.obj_id}"}
    label = labels.get(change.kind, f"T{change.obj_id}")
    if change.kind == "criterion":
        label = f"criterion #{change.obj_id}"
    return f"{label} {_short(change.title, 40)}".rstrip()


def approval_payload(result: ApprovalResult, plan: Plan) -> dict:
    """JSON payload for one approval."""
    return {
        "plan": plan.id,
        "name": plan.name,
        "created": result.created,
        "acknowledged": result.acknowledged,
        "revision": _revision_payload(result.revision),
    }


def approval_text(result: ApprovalResult, plan: Plan) -> str:
    """Human line for one approval."""
    revision = result.revision
    if not result.created:
        return f"P{plan.id} already approved at r{revision.revision}"
    suffix = f" ({result.acknowledged} changes)" if result.acknowledged else ""
    return f"approved P{plan.id} r{revision.revision}{suffix}"


def approval_row(result: ApprovalResult, plan: Plan) -> str:
    """Porcelain row for one approval."""
    return porcelain.row(
        "plan",
        plan.id,
        "approved" if result.created else "unchanged",
        plan.name,
        "-",
        f"r{result.revision.revision} {result.acknowledged}",
    )


def revisions_payload(entries: list[RevisionEntry], plan: Plan) -> list[dict]:
    """JSON payload for one plan's approval history."""
    return [
        {
            "plan": plan.id,
            "revision": entry.revision.revision,
            "approved_at": entry.revision.approved_at,
            "actor": entry.revision.actor,
            "reason": entry.revision.reason,
            "enforced": entry.revision.enforced,
            "changes": entry.changes,
        }
        for entry in entries
    ]


def revisions_text(entries: list[RevisionEntry], plan: Plan) -> str:
    """Human approval history, one revision per line."""
    if not entries:
        return f"P{plan.id} has no approved revision"
    lines: list[str] = []
    for entry in entries:
        revision = entry.revision
        plural = "change" if entry.changes == 1 else "changes"
        flags = " [enforced]" if revision.enforced else ""
        reason = f"  {_short(revision.reason, 50)}" if revision.reason else ""
        lines.append(
            f"r{revision.revision} {_date(revision.approved_at)} "
            f"@{revision.actor} {entry.changes} {plural}{flags}{reason}"
        )
    return "\n".join(lines)


def revisions_rows(entries: list[RevisionEntry], plan: Plan) -> list[str]:
    """Porcelain rows for one plan's approval history."""
    return [
        porcelain.row(
            "revision",
            entry.revision.revision,
            "approved",
            entry.revision.reason or "-",
            f"plan:{plan.id}",
            f"{entry.changes} changes @{entry.revision.actor}",
        )
        for entry in entries
    ]


def diff_payload(result: DiffResult, plan: Plan) -> dict:
    """JSON payload for one drift report."""
    return {
        "plan": plan.id,
        "name": plan.name,
        "from": _revision_payload(result.from_revision),
        "to": None if result.to_revision is None else _revision_payload(result.to_revision),
        "drifted": result.drifted,
        "summary": result.summary,
        "changes": [
            {
                "kind": entry.change.kind,
                "action": entry.change.action,
                "id": entry.change.obj_id,
                "identity": entry.change.identity,
                "title": entry.change.title,
                "field": entry.change.field,
                "before": entry.change.before,
                "after": entry.change.after,
                "parent": entry.change.parent,
                "reason": entry.reason,
                "actor": entry.actor,
                "ts": entry.ts,
                "change_id": entry.change_id,
            }
            for entry in result.entries
        ],
    }


def diff_text(result: DiffResult, plan: Plan) -> str:
    """Human drift report grouped by one line per change."""
    revision = result.from_revision
    if not result.drifted:
        return (
            f"P{plan.id} is in sync with r{revision.revision} "
            f"({_date(revision.approved_at)}, @{revision.actor})"
        )
    total = result.summary["total"]
    plural = "change" if total == 1 else "changes"
    lines = [
        f"P{plan.id} has {total} scope {plural} since r{revision.revision} "
        f"({_date(revision.approved_at)}, @{revision.actor})"
    ]
    for entry in result.entries:
        change = entry.change
        if change.action == "add":
            lines.append(f"  + {_label(entry)} (added; {_reason(entry)})")
        elif change.action == "remove":
            lines.append(f"  - {_label(entry)} (removed; {_reason(entry)})")
        elif change.action == "move":
            lines.append(
                f"  > {_label(entry)} moved {change.before} -> {change.after} ({_reason(entry)})"
            )
        else:
            lines.append(
                f"  ~ {_label(entry)} {change.field}: "
                f"{_short(change.before)!r} -> {_short(change.after)!r} "
                f"({_reason(entry)})"
            )
    return "\n".join(lines)


def diff_rows(result: DiffResult, plan: Plan) -> list[str]:
    """Porcelain rows for one drift report."""
    rows = [
        porcelain.row(
            "drift",
            entry.change.obj_id,
            entry.change.action,
            entry.change.title,
            f"{entry.change.kind}:{entry.change.obj_id}",
            entry.reason or "-",
        )
        for entry in result.entries
    ]
    revision = result.from_revision
    rows.append(
        porcelain.plan_row(
            plan.id,
            "drift" if result.drifted else "sync",
            plan.name,
            f"r{revision.revision} {result.summary['total']}",
        )
    )
    return rows
