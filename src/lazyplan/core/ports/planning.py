"""The planning repository port: rows, trees, criteria, and events."""

from __future__ import annotations

from typing import Protocol

from ..entities import Criterion, Milestone, Plan, Status, Task


class PlanningPort(Protocol):
    """Persistence surface the planning use cases need."""

    path: str

    def add_plan(
        self,
        name: str,
        description: str = "",
        goal: str = "",
        actor: str = "human",
    ) -> Plan: ...

    def add_milestone(
        self,
        plan_id: int,
        title: str,
        description: str = "",
        actor: str = "human",
    ) -> Milestone: ...

    def add_task(
        self,
        milestone_id: int,
        title: str,
        description: str = "",
        actor: str = "human",
    ) -> Task: ...

    def add_criteria(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str = "human",
    ) -> Criterion: ...

    def get_plan(self, pid: int) -> Plan | None: ...

    def get_milestone(self, sid: int) -> Milestone | None: ...

    def get_task(self, tid: int) -> Task | None: ...

    def get_parent(self, kind: str, obj_id: int) -> Plan | Milestone | Task | None: ...

    def list_plans(self) -> list[Plan]: ...

    def list_milestones(self, plan_id: int) -> list[Milestone]: ...

    def list_tasks(self, milestone_id: int) -> list[Task]: ...

    def milestones_map(self) -> dict[int, list[Milestone]]: ...

    def tasks_map(self) -> dict[int, list[Task]]: ...

    def criteria_map(self) -> dict[tuple[str, int], list[Criterion]]: ...

    def repos_map(self) -> dict[tuple[str, int], list[dict]]: ...

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]: ...

    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool: ...

    def log(self, actor: str, kind: str, action: str, detail: str = "") -> None: ...

    def feed(self, limit: int = 20) -> list[dict]: ...

    def counts(self) -> dict[str, int]: ...

    def fingerprint(self) -> tuple: ...
