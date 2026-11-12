"""Render one plan-scope diff as a grouped, reviewable model."""

from __future__ import annotations

from dataclasses import dataclass

from ....services.revisions import DiffEntry, DiffResult
from ...shared.design import truncate

_GLYPH = {"add": "+", "remove": "-", "change": "~", "move": "→"}
_ORDER = ("plan", "milestone", "task", "criterion")
_LABELS = {
    "plan": "plan",
    "milestone": "milestones",
    "task": "tasks",
    "criterion": "criteria",
}


@dataclass(frozen=True)
class DiffRow:
    """One scope change ready to paint."""

    action: str
    glyph: str
    kind: str
    obj_id: int
    title: str
    field: str = ""
    before: str = ""
    after: str = ""
    reason: str = ""


@dataclass(frozen=True)
class DiffGroup:
    """Changes of one kind, in stable order."""

    kind: str
    label: str
    rows: tuple[DiffRow, ...]


@dataclass(frozen=True)
class PlanDiffView:
    """A complete plan-scope diff: counts, groups, and empty state."""

    plan_id: int
    from_revision: int
    total: int
    summary: dict[str, int]
    groups: tuple[DiffGroup, ...]

    @property
    def empty(self) -> bool:
        """True when the live plan matches the approved revision."""
        return self.total == 0


def _excerpt(text: str, limit: int) -> str:
    """Collapse whitespace and trim long scope text for a preview row."""
    flat = " ".join(text.split())
    return truncate(flat, limit)


def _row(entry: DiffEntry, limit: int) -> DiffRow:
    """One flat row from a diff entry."""
    change = entry.change
    return DiffRow(
        action=change.action,
        glyph=_GLYPH.get(change.action, "?"),
        kind=change.kind,
        obj_id=change.obj_id,
        title=change.title,
        field=change.field,
        before=_excerpt(change.before, limit),
        after=_excerpt(change.after, limit),
        reason=_excerpt(entry.reason, limit),
    )


def build_plan_diff(result: DiffResult, max_text: int = 240) -> PlanDiffView:
    """Group a diff result by row kind for the dedicated screen."""
    rows = [_row(entry, max_text) for entry in result.entries]
    groups: list[DiffGroup] = []
    for kind in _ORDER:
        selected = tuple(row for row in rows if row.kind == kind)
        if selected:
            groups.append(DiffGroup(kind=kind, label=_LABELS[kind], rows=selected))
    return PlanDiffView(
        plan_id=result.plan_id,
        from_revision=result.from_revision.revision,
        total=result.summary.get("total", len(rows)),
        summary=dict(result.summary),
        groups=tuple(groups),
    )


def diff_text(result: DiffResult) -> str:
    """One scannable text diff: summary first, then each change and reason."""
    view = build_plan_diff(result)
    lines = [
        f"P{result.plan_id} diff from r{result.from_revision.revision}",
        "",
        f"{view.total} changes · +{view.summary.get('add', 0)}"
        f" -{view.summary.get('remove', 0)}"
        f" ~{view.summary.get('change', 0)}"
        f" →{view.summary.get('move', 0)}",
    ]
    if view.empty:
        lines.extend(["", "in sync with the approved revision"])
        return "\n".join(lines)
    for group in view.groups:
        lines.extend(["", group.label.upper()])
        for row in group.rows:
            label = f" {row.glyph} {row.kind} {row.obj_id} {row.title}".rstrip()
            if row.field:
                label += f" · {row.field}"
            lines.append(label)
            if row.action in ("change", "move") and (row.before or row.after):
                lines.append(f"  {row.before or '-'} → {row.after or '-'}")
            if row.reason:
                lines.append(f"  reason: {row.reason}")
    return "\n".join(lines)
