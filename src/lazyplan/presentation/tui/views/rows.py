"""Row renderables shared by the tree and the spinner."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from rich.text import Text

from ....core.entities import Status
from ...shared.design import milestone_row, plan_row, task_row

if TYPE_CHECKING:
    from ....core.entities import Milestone, Plan, Task
    from ....store import Store


@dataclass(frozen=True)
class RowSpec:
    """One tree row that can render at any width."""

    render: Callable[..., str]
    depth: int
    status: Status

    def markup(self, width: int) -> str:
        """Return this row's Rich markup at *width* cells."""
        return self.render(width=width)


def plan_spec(plan: Plan, progress: dict, source_stats: dict) -> RowSpec:
    """Build the width-independent renderer for one plan row."""
    stats = source_stats.get(("plan", plan.id))
    return RowSpec(
        render=partial(
            plan_row,
            plan,
            progress=progress.get(("plan", plan.id)),
            source_counts=(stats[0], stats[1], stats[2]) if stats else None,
        ),
        depth=3,
        status=plan.status,
    )


def milestone_spec(
    milestone: Milestone, store: Store, progress: dict, source_stats: dict
) -> RowSpec:
    """Build the width-independent renderer for one milestone row."""
    stats = source_stats.get(("milestone", milestone.id))
    return RowSpec(
        render=partial(
            milestone_row,
            milestone,
            store,
            progress=progress.get(("milestone", milestone.id)),
            source_counts=(stats[0], stats[1], stats[2]) if stats else None,
        ),
        depth=7,
        status=milestone.status,
    )


def task_spec(
    task: Task, store: Store, forge_map: dict, vcs_map: dict, claims_map: dict
) -> RowSpec:
    """Build the width-independent renderer for one task row."""
    prs = forge_map.get(("task", task.id), [])
    pr = prs[0] if prs else None
    links = vcs_map.get(("task", task.id), [])
    claim = claims_map.get(task.id)
    return RowSpec(
        render=partial(
            task_row,
            task,
            store,
            links=[link.sha for link in links],
            pr_state=pr.state if pr else "",
            pr_checks=pr.checks if pr else "",
            stale=any(link.stale for link in links),
            claim_actor=claim.actor if claim else "",
            claim_expired=claim.expired(time.time()) if claim else False,
            blocked=task.blocked,
        ),
        depth=11,
        status=task.status,
    )


def row_text(markup: str) -> Text:
    """Parse one row's canonical markup once into a Rich Text renderable."""
    return Text.from_markup(markup)
