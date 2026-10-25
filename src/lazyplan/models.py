"""Domain entities. Pure dataclasses.

Minimal journal model: plans carry a title, a why, a what, and acceptance
criteria. Milestones break a plan down; tasks break a milestone down.
Every level has title + details + status. Nothing else.
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


#: Where acceptance criteria may live.
CRITERION_PARENTS = KINDS


@dataclass
class Plan:
    """A unit of planned work: title + why + what + acceptance criteria."""

    id: int
    name: str
    description: str = ""  # the what
    status: Status = Status.TODO
    goal: str = ""  # the why

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("plan name must not be empty")


@dataclass
class Task:
    """An atomic unit of work under a milestone."""

    id: int
    milestone_id: int
    title: str
    status: Status = Status.TODO
    description: str = ""  # details / context for whoever picks this up

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("task title must not be empty")


@dataclass(frozen=True)
class Claim:
    """A time-limited lease on a task, held by one actor."""

    task_id: int
    actor: str
    started_at: float
    expires_at: float
    renewed_at: float = 0.0
    note: str = ""

    def expired(self, now: float) -> bool:
        """True when the lease is no longer active at `now`."""
        return self.expires_at <= now


@dataclass
class Milestone:
    """A slice of a plan, broken into tasks."""

    id: int
    plan_id: int
    title: str
    description: str = ""
    status: Status = Status.TODO

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("milestone title must not be empty")


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
    files: tuple[str, ...] = ()
    stale: bool = False
    checked_at: int = 0

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        sha = self.sha.strip().lower()
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("sha must be a 40-char hex commit hash")
        self.sha = sha


@dataclass
class ForgeLink:
    """One pull request or issue linked to a plan, milestone, or task."""

    id: int
    parent_kind: str  # "plan" | "milestone" | "task"
    parent_id: int
    provider: str = "github"
    kind: str = "pull"
    number: int = 0
    url: str = ""
    title: str = ""
    state: str = ""
    checks: str = ""
    reviews: str = ""
    author: str = ""
    base_ref: str = ""
    head_ref: str = ""
    merged_at: str = ""
    merge_commit_sha: str = ""
    updated_at: int = 0
    stale: bool = False
    payload: str = ""

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        if self.number <= 0:
            raise ValueError("forge link number must be positive")
        if not self.provider.strip():
            raise ValueError("forge link provider must not be empty")
        if not self.kind.strip():
            raise ValueError("forge link kind must not be empty")
