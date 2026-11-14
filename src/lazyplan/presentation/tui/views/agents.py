"""Claim rows for the agents panel: who holds which task, and for how long.

Pure formatting: no Textual imports, so tests can render rows without a
terminal. A row exists only while a claim does.
"""

from __future__ import annotations

from typing import Any

from ...shared.design import escape_markup, truncate

TASK_SHARE = 0.6
MIN_TITLE = 6


def age(started_at: float, stamp: float) -> str:
    """Compact age: minutes until an hour, then hours and minutes."""
    minutes = int(max(0.0, stamp - started_at) / 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


def rank_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest claim first."""
    return sorted(claims, key=lambda claim: -float(claim["started_at"]))


def _titles(task: str, plan: str, budget: int | None) -> tuple[str, str]:
    """Task and plan titles cut to share the cells left in a row."""
    if budget is None:
        return task, plan
    room = max(budget, 2 * MIN_TITLE)
    task_room = max(MIN_TITLE, int(room * TASK_SHARE))
    return truncate(task, task_room), truncate(plan, max(MIN_TITLE, room - task_room))


def claim_line(claim: dict[str, Any], now: float, width: int | None = None) -> str:
    """One row: ``@actor T12 task title · P3 plan title · 5m``."""
    actor = str(claim["actor"])
    task_id = f"T{claim['task_id']}"
    plan_id = f"P{claim['plan_id']}"
    elapsed = age(float(claim["started_at"]), now)
    fixed = len(f"@{actor} {task_id}  ·  {plan_id}  · {elapsed}")
    budget = None if width is None else width - fixed
    task, plan = _titles(str(claim["task_title"]), str(claim["plan_title"]), budget)
    return (
        f"[bold]@{escape_markup(actor)}[/] [dim]{task_id}[/] {escape_markup(task)}"
        f" · [dim]{plan_id}[/] {escape_markup(plan)} · [dim]{elapsed}[/]"
    )


def claims_summary(claims: list[dict[str, Any]]) -> str:
    """Border subtitle: how many tasks are held and by how many agents."""
    actors = {str(claim["actor"]) for claim in claims}
    tasks = f"{len(claims)} {'task' if len(claims) == 1 else 'tasks'}"
    return f"{tasks} · {len(actors)} {'agent' if len(actors) == 1 else 'agents'}"
