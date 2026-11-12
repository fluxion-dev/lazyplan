"""Strict parsing for plan status event details.

Trim and the archive/finished policy share this parser so a status event that
the policy ignores can never displace one it reads.
"""

from __future__ import annotations

#: SQLite stores integers as signed 64-bit values; a UDF must stay in range.
SQLITE_INT_MIN = -(2**63)
SQLITE_INT_MAX = 2**63 - 1


def parse_plan_status_detail(detail: str) -> tuple[int, str] | None:
    """Return ``(plan_id, target)`` for a policy status event, else None.

    Mirrors the long-standing ``plan_status_events_map`` rules: a
    case-sensitive ``plan #`` prefix, one `` -> `` separator, and a plan id
    accepted by strict Python ``int`` parsing.
    """
    text = str(detail or "").removesuffix(" (rollup)")
    if not text.startswith("plan #"):
        return None
    body = text[len("plan #") :]
    try:
        plan_text, target = body.split(" -> ", 1)
        plan_id = int(plan_text)
    except (TypeError, ValueError):
        return None
    return plan_id, target


def sqlite_plan_status_id(detail: str) -> int | None:
    """Plan id for the SQLite UDF, or None when malformed or out of int64 range."""
    parsed = parse_plan_status_detail(detail)
    if parsed is None:
        return None
    plan_id = parsed[0]
    if plan_id < SQLITE_INT_MIN or plan_id > SQLITE_INT_MAX:
        return None
    return plan_id
