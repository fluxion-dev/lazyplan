"""The planning repository port: rows, trees, criteria, and events."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol

from ..entities import Criterion, Milestone, Plan, PlanQuestion, Status, Task


class PlanningPort(Protocol):
    """Persistence surface the planning use cases need."""

    @property
    def db_path(self) -> str: ...

    def transaction(self) -> AbstractContextManager[None]: ...

    def set_entity_key(self, kind: str, row_id: int, key: str, actor: str = "human") -> None: ...

    def get_entity_key(self, kind: str, key: str) -> int | None: ...

    def entity_keys_map(self) -> dict[tuple[str, int], str]: ...

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
        reason: str = "",
    ) -> Milestone: ...

    def add_task(
        self,
        milestone_id: int,
        title: str,
        description: str = "",
        actor: str = "human",
        reason: str = "",
    ) -> Task: ...

    def add_criteria(
        self,
        parent_kind: str,
        parent_id: int,
        text: str,
        actor: str = "human",
        reason: str = "",
    ) -> Criterion: ...

    def get_plan(self, pid: int) -> Plan | None: ...

    def get_milestone(self, sid: int) -> Milestone | None: ...

    def get_task(self, tid: int) -> Task | None: ...

    def get_parent(self, kind: str, obj_id: int) -> Plan | Milestone | Task | None: ...

    def get_full(self, kind: str, obj_id: int) -> dict | None: ...

    def update_plan(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        actor: str = "human",
        reason: str = "",
    ) -> Plan | None: ...

    def update_milestone(
        self,
        sid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
        reason: str = "",
    ) -> Milestone | None: ...

    def update_task(
        self,
        tid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
        reason: str = "",
    ) -> Task | None: ...

    def delete(self, kind: str, obj_id: int, actor: str = "human", reason: str = "") -> bool: ...

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]: ...

    def get_criterion(self, cid: int) -> Criterion | None: ...

    def open_criteria(self, kind: str, obj_id: int) -> list[Criterion]: ...

    def set_criteria(self, cid: int, done: bool, actor: str = "human") -> Criterion | None: ...

    def update_criterion(
        self, cid: int, text: str, actor: str = "human", reason: str = ""
    ) -> Criterion | None: ...

    def delete_criteria(self, cid: int, actor: str = "human", reason: str = "") -> bool: ...

    def relate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool: ...

    def unrelate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool: ...

    def add_question(self, plan_id: int, text: str, actor: str = "human") -> PlanQuestion: ...

    def restore_question(
        self,
        plan_id: int,
        text: str,
        status: str = "open",
        actor: str = "human",
        ts: float = 0.0,
        resolved_at: float = 0.0,
        resolved_by: str = "",
        resolution: str = "",
    ) -> PlanQuestion | None: ...

    def get_question(self, qid: int) -> PlanQuestion | None: ...

    def list_questions(self, plan_id: int, status: str = "open") -> list[PlanQuestion]: ...

    def resolve_question(
        self, qid: int, note: str = "", actor: str = "human"
    ) -> PlanQuestion | None: ...

    def reopen_question(
        self, qid: int, note: str = "", actor: str = "human"
    ) -> PlanQuestion | None: ...

    def questions_map(self) -> dict[int, list[PlanQuestion]]: ...

    def list_plans(self) -> list[Plan]: ...

    def list_milestones(self, plan_id: int) -> list[Milestone]: ...

    def list_tasks(self, milestone_id: int) -> list[Task]: ...

    def milestones_map(self) -> dict[int, list[Milestone]]: ...

    def tasks_map(self) -> dict[int, list[Task]]: ...

    def criteria_map(self) -> dict[tuple[str, int], list[Criterion]]: ...

    def repos_map(self) -> dict[tuple[str, int], list[dict]]: ...

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]: ...

    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool: ...

    def log(
        self,
        actor: str,
        kind: str,
        action: str,
        detail: str = "",
        session_id: int | None = None,
    ) -> None: ...

    def feed(self, limit: int = 20) -> list[dict]: ...

    def counts(self) -> dict[str, int]: ...

    def fingerprint(self) -> tuple: ...
