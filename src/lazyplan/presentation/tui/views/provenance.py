"""Pure helpers for provenance and activity previews."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping

_OWNER = re.compile(r"^([PTM])(\d+)\b")
_TARGET = re.compile(r"\b(plan|milestone|task|criterion|question|session|comment|note)\s*#?(\d+)")
_SHORT_TARGET = re.compile(r"\b([PTMCQS])\s*#?(\d+)\b")
_LETTER_KIND = {
    "P": "plan",
    "T": "task",
    "M": "milestone",
    "C": "criterion",
    "Q": "question",
    "S": "session",
}


def owner_target(labels: tuple[str, ...]) -> tuple[str, int] | None:
    """First plan/milestone/task owner encoded in a source label list."""
    for label in labels:
        match = _OWNER.match(label.strip())
        if match:
            return _LETTER_KIND[match.group(1)], int(match.group(2))
    return None


def event_target(event: Mapping[str, object]) -> tuple[str, int] | None:
    """Owning plan, milestone, or task encoded in one feed event, if any."""
    detail = str(event.get("detail", "") or "")
    for match in _TARGET.finditer(detail):
        kind = match.group(1)
        if kind in ("plan", "milestone", "task"):
            return kind, int(match.group(2))
    for short in _SHORT_TARGET.finditer(detail):
        kind = _LETTER_KIND.get(short.group(1))
        if kind in ("plan", "milestone", "task"):
            return kind, int(short.group(2))
    kind = str(event.get("kind", "") or "")
    if kind in ("plan", "milestone", "task"):
        action = str(event.get("action", "") or "")
        fallback = re.search(r"#?(\d+)", detail or action)
        if fallback:
            return kind, int(fallback.group(1))
    return None


def event_label(event: Mapping[str, object]) -> str:
    """Compact one-line label for a feed row."""
    raw = event.get("ts")
    stamp = float(raw) if isinstance(raw, (int, float, str)) and raw else 0.0
    when = time.strftime("%m-%d %H:%M", time.localtime(stamp)) if stamp else ""
    actor = str(event.get("actor", "") or "")
    kind = str(event.get("kind", "") or "")
    action = str(event.get("action", "") or "")
    detail = str(event.get("detail", "") or "")
    return f"{when} @{actor} {kind}/{action} {detail}".strip()


def event_body(event: Mapping[str, object]) -> str:
    """Detail preview for one feed row, including its jump target."""
    target = event_target(event)
    lines = [
        f"event #{event.get('id', '')}",
        f"actor   @{event.get('actor', '')}",
        f"kind    {event.get('kind', '')}",
        f"action  {event.get('action', '')}",
        f"detail  {event.get('detail', '')}",
    ]
    if target is not None:
        kind, oid = target
        lines.append(f"target  {kind} #{oid}")
    else:
        lines.append("target  —")
    return "\n".join(lines)


__all__ = ["event_body", "event_label", "event_target", "owner_target"]
