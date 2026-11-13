"""Render one plan-scope diff as a grouped, reviewable model."""

from __future__ import annotations

from dataclasses import dataclass

from ....services.revisions import DiffEntry, DiffResult
from ...shared.design import escape_markup, truncate
from .diff_style import ACTION_GLYPH, ACTION_SLOT, DiffPalette

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
        glyph=ACTION_GLYPH.get(change.action, "?"),
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


def _action_color(palette: DiffPalette, action: str) -> str:
    """Palette colour for one scope action."""
    slot = ACTION_SLOT.get(action, "hunk")
    return getattr(palette, slot, palette.context)


def _head(view: PlanDiffView, palette: DiffPalette) -> str:
    """Head line plus one summary chip per action."""
    head = f"[bold]P{view.plan_id} scope diff[/] [dim]from r{view.from_revision}[/]"
    chips = [f"[reverse] {view.total} changes [/]"]
    for action in ("add", "remove", "change", "move"):
        count = view.summary.get(action, 0)
        if count:
            chips.append(f"[{_action_color(palette, action)}]{count} {action}[/]")
    return f"{head}\n{' '.join(chips)}"


def _row_lines(row: DiffRow, palette: DiffPalette) -> list[str]:
    """One change: its identity, before/after blocks, and reason."""
    color = _action_color(palette, row.action)
    ident = f"{row.kind} {row.obj_id}"
    line = f"[{color}]{row.glyph}[/] [bold]{escape_markup(ident)}[/] {escape_markup(row.title)}"
    if row.field:
        line += f" [dim]· {escape_markup(row.field)}[/]"
    lines = [line]
    if row.action in ("change", "move"):
        if row.before:
            lines.append(f"  [{palette.remove}]− {escape_markup(row.before)}[/]")
        if row.after:
            lines.append(f"  [{palette.add}]+ {escape_markup(row.after)}[/]")
    if row.reason:
        lines.append(f"  [{palette.context}]reason: {escape_markup(row.reason)}[/]")
    return lines


def _group_lines(group: DiffGroup, palette: DiffPalette) -> list[str]:
    """One section header and its change rows."""
    lines = [f"[bold {palette.hunk}]{group.label.upper()}[/] [dim]{len(group.rows)}[/]"]
    for row in group.rows:
        lines.extend(_row_lines(row, palette))
    return lines


def render_plan_diff(
    view: PlanDiffView,
    palette: DiffPalette | None = None,
) -> tuple[str, str]:
    """Return the head and body markup for the dedicated plan diff screen."""
    palette = palette or DiffPalette()
    head = _head(view, palette)
    if view.empty:
        return head, f"[{palette.add}]✓[/] [dim]in sync with the approved revision[/]"
    lines: list[str] = []
    for group in view.groups:
        if lines:
            lines.append("")
        lines.extend(_group_lines(group, palette))
    return head, "\n".join(lines)


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
