"""Shared action-bar markup for full screens that are not the main shell."""

from __future__ import annotations


def action_bar(
    primary: tuple[str, str] | None,
    items: list[tuple[str, str]],
    empty: str = "esc back",
) -> str:
    """Render one action bar with the primary key reversed.

    `items` are (key, label) pairs; the primary pair is skipped from the rest.
    """
    parts: list[str] = []
    primary_key = ""
    if primary is not None:
        primary_key, primary_label = primary
        parts.append(f"[reverse] {primary_key} [/]{primary_label}")
    for key, label in items:
        if not key or key == primary_key:
            continue
        parts.append(f"[dim]{key}[/] {label}")
    return " · ".join(parts) if parts else empty


__all__ = ["action_bar"]
