"""Domain entities. Pure dataclasses; SQLite dates stored as ISO YYYY-MM-DD strings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    """Task lifecycle states."""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class RiskStatus(StrEnum):
    """Risk lifecycle states."""

    OPEN = "open"
    MITIGATED = "mitigated"
    RETIRED = "retired"


PRIORITIES = ("p0", "p1", "p2", "p3")
PRIORITY_RANK = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "": 99}


def normalize_labels(raw: list[str]) -> list[str]:
    """Lowercase, dedupe, and drop blanks."""
    seen: set[str] = set()
    clean: list[str] = []
    for item in raw:
        label = item.strip().lower()
        if label and label not in seen:
            seen.add(label)
            clean.append(label)
    return clean


def parse_id_list(raw: str) -> list[int]:
    """Comma-separated ids → sorted unique ints. "" → []."""
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError as exc:
            raise ValueError(f"bad id in list: {part!r}") from exc
    return sorted(ids)


def format_id_list(ids: list[int]) -> str:
    """Sorted unique ints to a comma string."""
    return ",".join(str(i) for i in sorted(set(ids)))


@dataclass
class Project:
    """A container of work with narrative, dates, and status."""

    id: int
    name: str
    description: str = ""
    start_date: str = ""  # YYYY-MM-DD or ""
    end_date: str = ""
    status: Status = Status.TODO
    goal: str = ""  # 1-2 sentences: why this exists
    success_metrics: str = ""  # how we know it worked (lines)
    scope_in: str = ""  # explicitly in scope
    scope_out: str = ""  # explicitly out of scope
    assumptions: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name must not be empty")


@dataclass
class Task:
    """An atomic unit of work."""

    id: int
    story_id: int
    title: str
    status: Status = Status.TODO
    estimate: str = ""  # free text e.g. "2h", "3d"
    start_date: str = ""  # YYYY-MM-DD or "" (M4: tasks on gantt)
    end_date: str = ""
    description: str = ""  # context/notes for whoever (or whatever) picks this up
    owner: str = ""  # person or agent id responsible; "" = unassigned
    priority: str = ""  # "" | p0..p3
    labels: list[str] = field(default_factory=list)
    blocked_by: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("task title must not be empty")
        if self.priority not in ("", *PRIORITIES):
            raise ValueError(f"priority must be one of p0..p3, got {self.priority!r}")
        self.labels = normalize_labels(self.labels)
        for b in self.blocked_by:
            if not isinstance(b, int):
                raise ValueError(f"bad blocked_by id: {b!r}")


@dataclass
class UserStory:
    """A requirement with supporting materials and tasks."""

    id: int
    project_id: int
    title: str
    description: str = ""
    status: Status = Status.TODO
    start_date: str = ""
    end_date: str = ""
    owner: str = ""  # person or agent id responsible; "" = unassigned
    priority: str = ""  # "" | p0..p3
    labels: list[str] = field(default_factory=list)
    estimate: str = ""  # manual rough sizing; no auto-summed parsed effort
    blocked_by: list[int] = field(default_factory=list)  # same-kind ids

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("story title must not be empty")
        if self.priority not in ("", *PRIORITIES):
            raise ValueError(f"priority must be one of p0..p3, got {self.priority!r}")
        self.labels = normalize_labels(self.labels)
        for b in self.blocked_by:
            if not isinstance(b, int):
                raise ValueError(f"bad blocked_by id: {b!r}")


@dataclass
class Link:
    """Supporting material pointer: URL or file path attached to a story/task."""

    id: int
    parent_kind: str  # "story" | "task"
    parent_id: int
    url: str
    label: str = ""

    def __post_init__(self) -> None:
        if self.parent_kind not in ("story", "task"):
            raise ValueError("parent_kind must be story|task")
        if not self.url.strip():
            raise ValueError("link url must not be empty")


@dataclass
class Criterion:
    """One acceptance-checklist item on a story/task. Advisory, never blocking."""

    id: int
    parent_kind: str  # "story" | "task"
    parent_id: int
    text: str
    done: bool = False

    def __post_init__(self) -> None:
        if self.parent_kind not in ("story", "task"):
            raise ValueError("parent_kind must be story|task")
        if not self.text.strip():
            raise ValueError("criterion text must not be empty")


@dataclass
class Risk:
    """Project-level risk: likelihood x impact, mitigation, lifecycle."""

    id: int
    project_id: int
    title: str
    likelihood: str = "med"  # low | med | high
    impact: str = "med"  # low | med | high
    mitigation: str = ""
    status: RiskStatus = RiskStatus.OPEN

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("risk title must not be empty")
        if self.likelihood not in ("low", "med", "high"):
            raise ValueError("likelihood must be low|med|high")
        if self.impact not in ("low", "med", "high"):
            raise ValueError("impact must be low|med|high")


@dataclass
class Milestone:
    """A dated marker on a project's timeline, rendered on the gantt."""

    id: int
    project_id: int
    title: str
    date: str = ""  # YYYY-MM-DD

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("milestone title must not be empty")
