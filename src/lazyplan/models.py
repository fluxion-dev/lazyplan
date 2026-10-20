"""Domain entities. Pure dataclasses.

Minimal journal model: plans carry a title, a priority, a why, a what,
and acceptance criteria. Milestones break a plan down; tasks break a
milestone down. Every level has title + details + priority + status.
Nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .kinds import KINDS, PARENT_KIND_ERROR


class Status(StrEnum):
    """Lifecycle states."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"


PRIORITIES = ("p0", "p1", "p2", "p3")
PRIORITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "": 99}

#: New tasks land here unless a priority is given.
DEFAULT_TASK_PRIORITY = "p1"

#: Where acceptance criteria may live.
CRITERION_PARENTS = KINDS


def check_priority(priority: str) -> str:
    """Validate a priority value ("" clears)."""
    if priority not in ("", *PRIORITIES):
        raise ValueError(f"priority must be one of p0..p3, got {priority!r}")
    return priority


@dataclass
class Plan:
    """A unit of planned work: title + priority + why + what + acceptance criteria."""

    id: int
    name: str
    description: str = ""  # the what
    status: Status = Status.TODO
    goal: str = ""  # the why
    priority: str = ""  # "" | p0..p3

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("plan name must not be empty")
        check_priority(self.priority)


@dataclass
class Task:
    """An atomic unit of work under a milestone."""

    id: int
    milestone_id: int
    title: str
    status: Status = Status.TODO
    description: str = ""  # details / context for whoever picks this up
    priority: str = ""  # "" | p0..p3

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("task title must not be empty")
        check_priority(self.priority)


@dataclass
class Milestone:
    """A slice of a plan, broken into tasks."""

    id: int
    plan_id: int
    title: str
    description: str = ""
    status: Status = Status.TODO
    priority: str = ""  # "" | p0..p3

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("milestone title must not be empty")
        check_priority(self.priority)


@dataclass
class Criterion:
    """One acceptance-checklist item on a plan, milestone, or task. Advisory, never blocking."""

    id: int
    parent_kind: str  # "plan" | "milestone" | "task"
    parent_id: int
    text: str
    done: bool = False

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        if not self.text.strip():
            raise ValueError("criterion text must not be empty")


@dataclass
class VcsLink:
    """One commit linked to a plan, milestone, or task."""

    id: int
    parent_kind: str  # "plan" | "milestone" | "task"
    parent_id: int
    sha: str  # full 40-char commit hash
    subject: str = ""
    author: str = ""
    timestamp: int = 0
    repo_root: str = ""

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        sha = self.sha.strip().lower()
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("sha must be a 40-char hex commit hash")
        self.sha = sha
