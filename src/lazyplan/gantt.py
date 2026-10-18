"""ASCII gantt helpers. Shared by `lpui gantt` (agents/CI) and the Textual gantt view."""

from __future__ import annotations

from datetime import date, timedelta


def parse(d: str) -> date | None:
    """ISO YYYY-MM-DD to date, or None."""
    try:
        y, m, dd = (int(x) for x in d.split("-"))
        return date(y, m, dd)
    except (ValueError, AttributeError):
        return None


def span(dates: list[str], width: int = 40) -> tuple[date, date]:
    """Date range covering all given dates (minimum two weeks)."""
    parsed = [p for p in (parse(d) for d in dates) if p]
    if not parsed:
        today = date.today()
        return today, today + timedelta(days=14)
    lo, hi = min(parsed), max(parsed)
    if lo == hi:
        hi = lo + timedelta(days=7)
    return lo, hi


def bar(start: str, end: str, lo: date, hi: date, width: int = 40) -> str:
    """ASCII bar for [start, end] within [lo, hi]."""
    s, e = parse(start), parse(end)
    if not s or not e:
        return "·" * 0 + "(no dates)"
    total = max((hi - lo).days, 1)
    a = min(max((s - lo).days * width // total, 0), width - 1)
    b = min(max((e - lo).days * width // total, a + 1), width)
    return " " * a + "█" * (b - a) + " " * (width - b)
