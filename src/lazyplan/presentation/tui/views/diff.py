"""Render one plan diff for the read-only text overlay."""

from __future__ import annotations

from ....services.revisions import DiffResult

_GLYPH = {"add": "+", "remove": "-", "change": "~", "move": "→"}


def diff_text(result: DiffResult) -> str:
    """One scannable diff: summary first, then each change and its reason."""
    summary = result.summary
    lines = [
        f"P{result.plan_id} diff from r{result.from_revision.revision}",
        "",
        f"{summary['total']} changes · +{summary['add']} -{summary['remove']}"
        f" ~{summary['change']} →{summary['move']}",
    ]
    if not result.entries:
        lines.extend(["", "in sync with the approved revision"])
        return "\n".join(lines)
    for entry in result.entries:
        change = entry.change
        glyph = _GLYPH.get(change.action, "?")
        label = f"{glyph} {change.kind} {change.obj_id} {change.title}".rstrip()
        if change.field:
            label += f" · {change.field}"
        lines.extend(["", label])
        if change.action in ("change", "move") and (change.before or change.after):
            lines.append(f"  {change.before or '-'} → {change.after or '-'}")
        if entry.reason:
            lines.append(f"  reason: {entry.reason}")
    return "\n".join(lines)
