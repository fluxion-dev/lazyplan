"""Core domain entities. Pure dataclasses.

Minimal journal model: plans carry a title, a why, a what, and acceptance
criteria. Milestones break a plan down; tasks break a milestone down.
Every level has title + details + status. Nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .kinds import KINDS, PARENT_KIND_ERROR, QUESTION_STATUSES, SCOPE_KINDS


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
    blocked: bool = False
    blocked_reason: str = ""

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
    worktree: str = ""
    repo_path: str = ""

    def expired(self, now: float) -> bool:
        """True when the lease is no longer active at `now`."""
        return self.expires_at <= now


@dataclass(frozen=True)
class Session:
    """One agent working session with a summary and handoff."""

    id: int
    actor: str = "human"
    plan_id: int | None = None
    repo_path: str = ""
    branch: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    summary: str = ""
    handoff: str = ""
    phase: str = "working"
    last_seen_at: float = 0.0
    host: str = ""
    host_session: str = ""
    auto_closed: bool = False

    @property
    def ended(self) -> bool:
        """True when the session has been closed."""
        return self.ended_at > 0

    @property
    def awaiting(self) -> bool:
        """True when the agent finished its turn and waits on the user."""
        return not self.ended and self.phase == "awaiting"

    def last_activity(self) -> float:
        """Newest heartbeat, falling back to the start for old rows."""
        return self.last_seen_at if self.last_seen_at > 0 else self.started_at

    def idle_seconds(self, now: float) -> float:
        """Seconds since the last heartbeat while open; zero once ended."""
        if self.ended:
            return 0.0
        return max(now - self.last_activity(), 0.0)

    def duration(self, now: float) -> float:
        """Seconds between start and end, or start and *now* while open."""
        stop = self.ended_at if self.ended else now
        return max(stop - self.started_at, 0.0)


@dataclass(frozen=True)
class PlanRevision:
    """One human approval of a plan's scope, with its canonical snapshot."""

    id: int
    plan_id: int
    revision: int
    approved_at: float
    actor: str = "human"
    reason: str = ""
    digest: str = ""
    snapshot: str = ""
    change_mark: int = 0
    enforced: bool = False

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("revision must be at least 1")
        if len(self.digest) != 64 or any(c not in "0123456789abcdef" for c in self.digest):
            raise ValueError("digest must be a 64-char hex sha256")
        if not self.snapshot.strip():
            raise ValueError("snapshot must not be empty")
        if self.change_mark < 0:
            raise ValueError("change_mark must not be negative")


@dataclass(frozen=True)
class PlanChange:
    """One recorded scope-changing edit, with the reason the author gave."""

    id: int
    plan_id: int
    ts: float
    actor: str = "human"
    kind: str = "plan"
    obj_id: int = 0
    action: str = "edit"
    field: str = ""
    reason: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise ValueError(f"kind must be {'|'.join(SCOPE_KINDS)}")
        if self.action not in ("add", "edit", "delete"):
            raise ValueError("action must be add|edit|delete")
        if self.obj_id < 0:
            raise ValueError("obj_id must not be negative")


@dataclass(frozen=True)
class CriterionEvidence:
    """One recorded proof row for a criterion.

    lazyplan never executes the command, fetches the PR, or reads the artifact.
    The row is the agent's or CI's declaration, not a verified fact.
    """

    id: int
    criterion_id: int
    task_id: int | None = None
    command: str = ""
    exit_code: int | None = None
    commit_sha: str = ""
    pr_url: str = ""
    artifact_path: str = ""
    note: str = ""
    actor: str = "human"
    ts: float = 0.0

    def __post_init__(self) -> None:
        if self.criterion_id < 1:
            raise ValueError("criterion_id must be positive")
        if self.task_id is not None and self.task_id < 1:
            raise ValueError("task_id must be positive")
        if self.exit_code is not None and not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an integer or None")
        sha = self.commit_sha.strip().lower()
        if sha:
            if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
                raise ValueError("commit_sha must be a 40-char hex hash")
            object.__setattr__(self, "commit_sha", sha)
        if not any(
            (
                self.command.strip(),
                sha,
                self.pr_url.strip(),
                self.artifact_path.strip(),
                self.note.strip(),
            )
        ):
            raise ValueError("evidence needs a command, commit, PR, artifact, or note")

    @property
    def passing(self) -> bool:
        """True when the declared exit code is absent or zero."""
        return self.exit_code is None or self.exit_code == 0


@dataclass(frozen=True)
class ExternalRef:
    """A read-only pointer from a plan to an external epic, issue, or doc."""

    id: int
    plan_id: int
    url: str
    provider: str = "other"
    kind: str = "issue"
    external_id: str = ""
    title: str = ""
    state: str = ""
    actor: str = "human"
    created_at: float = 0.0


@dataclass(frozen=True)
class PlanQuestion:
    """One open or resolved question on a plan."""

    id: int
    plan_id: int
    text: str
    status: str = "open"
    actor: str = "human"
    ts: float = 0.0
    resolved_at: float = 0.0
    resolved_by: str = ""
    resolution: str = ""

    def __post_init__(self) -> None:
        if self.plan_id < 1:
            raise ValueError("plan_id must be positive")
        if not self.text.strip():
            raise ValueError("question text must not be empty")
        if self.status not in QUESTION_STATUSES:
            raise ValueError(f"status must be {'|'.join(QUESTION_STATUSES)}")


@dataclass(frozen=True)
class Note:
    """An append-only handoff note on a plan, milestone, or task."""

    id: int
    parent_kind: str
    parent_id: int
    text: str
    actor: str = "human"
    ts: float = 0.0

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        if not self.text.strip():
            raise ValueError("note text must not be empty")


@dataclass(frozen=True)
class Issue:
    """A provider issue normalized for import."""

    provider: str
    external_id: str
    number: str
    url: str
    title: str
    body: str = ""
    state: str = ""
    updated_at: float = 0.0


@dataclass(frozen=True)
class Comment:
    """A review comment on a plan, milestone, or task."""

    id: int
    parent_kind: str
    parent_id: int
    text: str
    actor: str = "human"
    ts: float = 0.0
    resolved: bool = False

    def __post_init__(self) -> None:
        if self.parent_kind not in CRITERION_PARENTS:
            raise ValueError(PARENT_KIND_ERROR)
        if not self.text.strip():
            raise ValueError("comment text must not be empty")


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


@dataclass(frozen=True)
class HookResult:
    """What a lifecycle hook wants the host to show or block."""

    text: str = ""
    context: bool = False
    block: str = ""

    def capped(self) -> HookResult:
        """Keep context and block reasons inside the host's patience."""
        return HookResult(self.text[:2000], self.context, self.block[:2000])
