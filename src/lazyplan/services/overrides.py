"""Manual override audit events.

One helper writes the feed row the human reviews: actor `tui`, kind `override`,
the action verb, and a target plus an optional reason. The detail uses the
same 500-character cap as every other event.
"""

from __future__ import annotations

from typing import Protocol

MAX_DETAIL = 500


class OverrideLogPort(Protocol):
    """The one store method this helper needs."""

    def log(
        self,
        actor: str,
        kind: str,
        action: str,
        detail: str = "",
        session_id: int | None = None,
    ) -> None: ...


def record_override(port: OverrideLogPort, action: str, target: str, reason: str = "") -> None:
    """Append one manual-override event, capped for the feed."""
    detail = f"{target.strip()}: {action.strip()}"
    clean_reason = reason.strip()
    if clean_reason:
        detail = f"{detail} — {clean_reason}"
    port.log("tui", "override", action.strip(), detail[:MAX_DETAIL])
