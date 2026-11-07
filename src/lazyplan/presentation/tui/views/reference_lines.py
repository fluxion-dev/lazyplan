"""One-line reference rows shared by the plan views."""

from __future__ import annotations

from typing import Any

from ...shared.design import escape_markup


def reference_lines(refs: list[dict[str, Any]]) -> tuple[str, ...]:
    """Read-only external reference rows, capped for scanning."""
    return tuple(
        f"  [dim]{escape_markup(str(ref.get('provider', 'other')))}/"
        f"{escape_markup(str(ref.get('kind', 'issue')))}[/] "
        f"{escape_markup(str(ref.get('title') or ref.get('url', '')))}"
        for ref in refs[:5]
    )
