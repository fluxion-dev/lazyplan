"""Row renderables shared by the tree and the spinner."""

from __future__ import annotations

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


def plan_spec(plan: Plan, progress: dict, attention: bool = False, worktrees: int = 0) -> RowSpec:
    """Build the width-independent renderer for one plan row."""
    return RowSpec(
        render=partial(
            plan_row,
            plan,
            progress=progress.get(("plan", plan.id)),
            attention=attention,
            worktrees=worktrees,
        ),
        depth=3,
        status=plan.status,
    )


def milestone_spec(
    milestone: Milestone, store: Store, progress: dict, attention: bool = False
) -> RowSpec:
    """Build the width-independent renderer for one milestone row."""
    return RowSpec(
        render=partial(
            milestone_row,
            milestone,
            store,
            progress=progress.get(("milestone", milestone.id)),
            attention=attention,
        ),
        depth=7,
        status=milestone.status,
    )


def task_spec(task: Task, attention: bool = False) -> RowSpec:
    """Build the width-independent renderer for one task row."""
    return RowSpec(
        render=partial(task_row, task, attention=attention),
        depth=11,
        status=task.status,
    )


def row_text(markup: str) -> Text:
    """Parse one row's canonical markup once into a Rich Text renderable."""
    return Text.from_markup(markup)
