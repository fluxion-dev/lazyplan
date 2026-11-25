"""Fresh-session task briefs with a hard context budget.

A task starts in a new session and rebuilds context from this brief. The brief
carries the plan, milestone, task contract, criteria, touch-points, and the
small amount of live context a worker needs; it must fit a fraction of the
model window so most of the window remains for the work itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..core.entities import Comment, Criterion, Milestone, Note, Plan, Task
from ..core.policies.context import (
    DEFAULT_TASK_CONTEXT_PERCENT,
    budget_tokens,
    check_percent,
    check_window,
    estimate_tokens,
    percent_used,
)
from ..core.ports.insights import InsightsPort

_MAX_CONTEXT_ITEMS = 5
_MAX_PRIOR_TASKS = 3
_MAX_ITEM_CHARS = 400


class ContextBudgetError(ValueError):
    """A task's fresh-session brief exceeds its context budget."""


@dataclass(frozen=True)
class TaskBrief:
    """One task's measured starting context."""

    task_id: int
    plan_id: int
    milestone_id: int
    text: str
    chars: int
    tokens: int
    window: int
    budget: int
    budget_percent: int
    percent: float
    fits: bool

    def to_dict(self) -> dict[str, object]:
        """JSON-safe payload."""
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "milestone_id": self.milestone_id,
            "chars": self.chars,
            "tokens": self.tokens,
            "window": self.window,
            "budget": self.budget,
            "budget_percent": self.budget_percent,
            "percent": self.percent,
            "fits": self.fits,
            "text": self.text,
        }

    def require_fits(self) -> None:
        """Refuse this brief when it leaves too little window for the work."""
        if self.fits:
            return
        raise ContextBudgetError(
            f"T{self.task_id} fresh brief uses {self.tokens:,} tokens"
            f" ({self.percent}% of {self.window:,}); budget is {self.budget:,}"
            f" ({self.budget_percent}%). Split the task or trim its brief."
        )


def build(
    port: InsightsPort,
    task_id: int,
    window: int,
    percent: int = DEFAULT_TASK_CONTEXT_PERCENT,
    *,
    extra: str = "",
) -> TaskBrief:
    """Build and measure one task's fresh-session brief."""
    check_window(window)
    check_percent(percent)
    task = _task(port, task_id)
    milestone = _milestone(port, task.milestone_id)
    plan = _plan(port, milestone.plan_id)
    budget = budget_tokens(window, percent)
    text = "\n".join(
        [
            *_header(task, window, budget, percent),
            *_plan_section(port, plan),
            *_milestone_section(port, milestone),
            *_task_section(port, task),
            *_touchpoints(port, task),
            *_live_context(port, plan, milestone, task),
            *_finish_section(task),
            *_extra_section(extra),
        ]
    ).strip()
    text += "\n"
    tokens = estimate_tokens(text)
    return TaskBrief(
        task_id=task.id,
        plan_id=plan.id,
        milestone_id=milestone.id,
        text=text,
        chars=len(text),
        tokens=tokens,
        window=window,
        budget=budget,
        budget_percent=percent,
        percent=percent_used(tokens, window),
        fits=tokens <= budget,
    )


def _task(port: InsightsPort, task_id: int) -> Task:
    task = port.get_task(task_id)
    if task is None:
        raise KeyError(f"task #{task_id} not found")
    return task


def _milestone(port: InsightsPort, milestone_id: int) -> Milestone:
    milestone = port.get_milestone(milestone_id)
    if milestone is None:
        raise KeyError(f"milestone #{milestone_id} not found")
    return milestone


def _plan(port: InsightsPort, plan_id: int) -> Plan:
    plan = port.get_plan(plan_id)
    if plan is None:
        raise KeyError(f"plan #{plan_id} not found")
    return plan


def _header(task: Task, window: int, budget: int, percent: int) -> list[str]:
    return [
        f"# Fresh session for T{task.id}: {task.title}",
        "",
        "Start a new session for this task. Do not continue another task's conversation.",
        "Rebuild context from this brief; it is the whole starting context.",
        "",
        f"Session budget: {budget:,} tokens ({percent}% of a {window:,}-token window).",
        "Stop and split the task if reading, editing, or verification needs more.",
        "",
    ]


def _plan_section(port: InsightsPort, plan: Plan) -> list[str]:
    return [
        f"## Plan P{plan.id}: {plan.name}",
        f"Status: {plan.status.value}",
        "",
        "### Why",
        plan.goal or "(none recorded)",
        "",
        "### What",
        plan.description or "(none recorded)",
        "",
        "### Plan acceptance criteria",
        *_criteria(port.list_criteria("plan", plan.id)),
        "",
    ]


def _milestone_section(port: InsightsPort, milestone: Milestone) -> list[str]:
    return [
        f"## Milestone M{milestone.id}: {milestone.title}",
        f"Status: {milestone.status.value}; lane {milestone.lane_group}; role {milestone.agent_role}",
        "",
        milestone.description or "(none recorded)",
        "",
        "### Milestone acceptance criteria",
        *_criteria(port.list_criteria("milestone", milestone.id)),
        "",
    ]


def _task_section(port: InsightsPort, task: Task) -> list[str]:
    return [
        f"## Task T{task.id}: {task.title}",
        f"Status: {task.status.value}; role {task.role}",
        "",
        task.description or "(none recorded)",
        "",
        "### Task acceptance criteria",
        *_criteria(port.list_criteria("task", task.id)),
        "",
    ]


def _touchpoints(port: InsightsPort, task: Task) -> list[str]:
    paths = port.list_touchpoints(task.id)
    if not paths:
        return ["## Touch-points", "- (none declared)", ""]
    return ["## Touch-points", *(f"- {path}" for path in paths), ""]


def _live_context(
    port: InsightsPort,
    plan: Plan,
    milestone: Milestone,
    task: Task,
) -> list[str]:
    lines = ["## Live context"]
    prior = _prior_tasks(port, milestone, task)
    if prior:
        lines.extend(f"- Previous task: {row}" for row in prior)
    questions = port.list_questions(plan.id)
    if questions:
        lines.extend(
            f"- Open question Q{question.id}: {_capped(question.text)}"
            for question in questions[:_MAX_CONTEXT_ITEMS]
        )
    notes = [
        *_capped_items("plan", port.list_notes("plan", plan.id, limit=_MAX_CONTEXT_ITEMS)),
        *_capped_items(
            "milestone", port.list_notes("milestone", milestone.id, limit=_MAX_CONTEXT_ITEMS)
        ),
        *_capped_items("task", port.list_notes("task", task.id, limit=_MAX_CONTEXT_ITEMS)),
    ]
    if notes:
        lines.extend(f"- Note {item}" for item in notes[:_MAX_CONTEXT_ITEMS])
    comments = [
        *_open_comments("plan", port.list_comments("plan", plan.id)),
        *_open_comments("milestone", port.list_comments("milestone", milestone.id)),
        *_open_comments("task", port.list_comments("task", task.id)),
    ]
    if comments:
        lines.extend(f"- Comment {item}" for item in comments[:_MAX_CONTEXT_ITEMS])
    repos = port.list_repos("plan", plan.id)
    if repos:
        paths = ", ".join(str(row.get("repo_path", "")) for row in repos if row.get("repo_path"))
        if paths:
            lines.append(f"- Linked repos: {paths}")
    if len(lines) == 1:
        lines.append("- (none)")
    lines.append("")
    return lines


def _prior_tasks(port: InsightsPort, milestone: Milestone, task: Task) -> list[str]:
    rows = port.list_tasks(milestone.id)
    index = next((position for position, row in enumerate(rows) if row.id == task.id), None)
    if index is None:
        return []
    return [
        f"T{row.id} {row.title} ({row.status.value})"
        for row in rows[max(0, index - _MAX_PRIOR_TASKS) : index]
    ]


def _capped_items(kind: str, rows: Sequence[Note]) -> list[str]:
    items: list[str] = []
    for row in rows:
        actor = str(getattr(row, "actor", "human"))
        text = str(getattr(row, "text", "") or "")
        items.append(f"{kind} @{actor}: {_capped(text)}")
    return items


def _open_comments(kind: str, rows: Sequence[Comment]) -> list[str]:
    items: list[str] = []
    for row in rows:
        if bool(getattr(row, "resolved", False)):
            continue
        actor = str(getattr(row, "actor", "human"))
        text = str(getattr(row, "text", "") or "")
        items.append(f"{kind} @{actor}: {_capped(text)}")
    return items


def _criteria(rows: list[Criterion]) -> list[str]:
    if not rows:
        return ["- (none)"]
    return [f"- [{'x' if row.done else ' '}] {row.text}" for row in rows]


def _capped(text: str) -> str:
    value = " ".join(text.split())
    if len(value) <= _MAX_ITEM_CHARS:
        return value
    return value[: _MAX_ITEM_CHARS - 1].rstrip() + "…"


def _finish_section(task: Task) -> list[str]:
    return [
        "## Finish",
        f"1. Work only T{task.id}; do not start another task in this session.",
        "2. Commit small green slices and link each one to the task.",
        "3. Move the task done and leave a handoff note for the next session.",
        "4. End the session. The next task starts a new session and a new brief.",
        "5. If the work no longer fits the session budget, stop and split the task.",
        "",
    ]


def _extra_section(extra: str) -> list[str]:
    text = extra.strip()
    if not text:
        return []
    return ["## Session commands", text, ""]
