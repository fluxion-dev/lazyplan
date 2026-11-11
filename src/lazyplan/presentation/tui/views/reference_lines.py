"""One-line reference rows shared by the plan views."""

from __future__ import annotations

from typing import Any

from ...shared.design import escape_markdown


def reference_lines(refs: list[dict[str, Any]]) -> tuple[str, ...]:
    """Read-only external reference rows, capped for scanning."""
    rows: list[str] = []
    for ref in refs[:5]:
        provider = escape_markdown(str(ref.get("provider", "other")))
        kind = escape_markdown(str(ref.get("kind", "issue")))
        label = escape_markdown(str(ref.get("title") or ref.get("url", "")))
        url = str(ref.get("url") or "").strip().replace(">", "%3E").replace("\n", "")
        prefix = f"{provider}/{kind}"
        rows.append(f"- {prefix} [{label}](<{url}>)" if url else f"- {prefix} {label}")
    return tuple(rows)
