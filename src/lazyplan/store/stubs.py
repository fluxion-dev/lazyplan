"""Cross-domain Store method declarations for the mixins.

Every stub is overridden by one mixin; the stubs keep mypy strict aware of
the assembled `Store` API without duplicating imports at each call site."""

from __future__ import annotations

import sqlite3

from ..models import (
    Claim,
    Comment,
    Criterion,
    Milestone,
    Note,
    Plan,
    Task,
)
from .stubs_links import StoreStubsLinks

CLAIM_DEFAULT_TTL = 30 * 60


class StoreStubs(StoreStubsLinks):
    """Declarations filled in by the persistence mixins."""

    def add_plan(
        self, name: str, description: str = "", goal: str = "", actor: str = "human"
    ) -> Plan:
        raise NotImplementedError

    @staticmethod
    def _opt(r: sqlite3.Row, keys: set[str], name: str) -> str:
        raise NotImplementedError

    def _row_to_plan(self, r: sqlite3.Row) -> Plan:
        raise NotImplementedError

    def plan_uid(self, pid: int) -> str:
        raise NotImplementedError

    def set_plan_uid(self, pid: int, uid: str) -> bool:
        raise NotImplementedError

    def get_plan_by_uid(self, uid: str) -> Plan | None:
        raise NotImplementedError

    def get_plan(self, pid: int) -> Plan | None:
        raise NotImplementedError

    def list_plans(self) -> list[Plan]:
        raise NotImplementedError

    def plan_uids_map(self) -> dict[int, str]:
        raise NotImplementedError

    def update_plan(
        self,
        pid: int,
        name: str | None = None,
        description: str | None = None,
        goal: str | None = None,
        actor: str = "human",
    ) -> Plan | None:
        raise NotImplementedError

    def add_milestone(
        self, plan_id: int, title: str, description: str = "", actor: str = "human"
    ) -> Milestone:
        raise NotImplementedError

    def _row_to_milestone(self, r: sqlite3.Row) -> Milestone:
        raise NotImplementedError

    def get_milestone(self, sid: int) -> Milestone | None:
        raise NotImplementedError

    def list_milestones(self, plan_id: int) -> list[Milestone]:
        raise NotImplementedError

    def milestones_map(self) -> dict[int, list[Milestone]]:
        raise NotImplementedError

    def update_milestone(
        self,
        sid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
    ) -> Milestone | None:
        raise NotImplementedError

    def add_task(
        self, milestone_id: int, title: str, description: str = "", actor: str = "human"
    ) -> Task:
        raise NotImplementedError

    def _row_to_task(self, r: sqlite3.Row) -> Task:
        raise NotImplementedError

    def get_task(self, tid: int) -> Task | None:
        raise NotImplementedError

    def list_tasks(self, milestone_id: int) -> list[Task]:
        raise NotImplementedError

    def tasks_map(self) -> dict[int, list[Task]]:
        raise NotImplementedError

    @staticmethod
    def _row_to_claim(r: sqlite3.Row) -> Claim:
        raise NotImplementedError

    @staticmethod
    def _ttl(value: float) -> float:
        raise NotImplementedError

    def claim_task(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = CLAIM_DEFAULT_TTL,
        note: str = "",
        force: bool = False,
        now: float | None = None,
    ) -> tuple[Claim, Claim | None]:
        raise NotImplementedError

    def renew_claim(
        self,
        task_id: int,
        actor: str,
        ttl_seconds: float = CLAIM_DEFAULT_TTL,
        now: float | None = None,
    ) -> Claim:
        raise NotImplementedError

    def release_claim(self, task_id: int, actor: str, force: bool = False) -> Claim | None:
        raise NotImplementedError

    def get_claim(self, task_id: int) -> Claim | None:
        raise NotImplementedError

    def claims_map(self) -> dict[int, Claim]:
        raise NotImplementedError

    def list_claims(
        self, include_expired: bool = False, now: float | None = None, plan_id: int | None = None
    ) -> list[dict]:
        raise NotImplementedError

    def restore_claim(
        self,
        task_id: int,
        actor: str,
        started_at: float,
        expires_at: float,
        renewed_at: float = 0,
        note: str = "",
    ) -> bool:
        raise NotImplementedError

    def next_claimable_task(
        self, plan_id: int | None = None, now: float | None = None
    ) -> Task | None:
        raise NotImplementedError

    @staticmethod
    def _row_to_note(r: sqlite3.Row) -> Note:
        raise NotImplementedError

    def add_note(self, parent_kind: str, parent_id: int, text: str, actor: str = "human") -> Note:
        raise NotImplementedError

    def list_notes(self, parent_kind: str, parent_id: int, limit: int | None = None) -> list[Note]:
        raise NotImplementedError

    def restore_note(
        self, parent_kind: str, parent_id: int, text: str, actor: str, ts: float
    ) -> Note | None:
        raise NotImplementedError

    def add_issue_link(
        self,
        provider: str,
        external_id: str,
        number: str,
        url: str,
        title: str,
        state: str,
        row_kind: str,
        row_id: int,
        updated_at: float = 0,
    ) -> dict:
        raise NotImplementedError

    def get_issue_link(self, provider: str, external_id: str) -> dict | None:
        raise NotImplementedError

    def list_issue_links(self, row_kind: str, row_id: int) -> list[dict]:
        raise NotImplementedError

    def issue_links_map(self) -> dict[tuple[str, int], list[dict]]:
        raise NotImplementedError

    def update_issue_link(
        self, provider: str, external_id: str, title: str, url: str, state: str, updated_at: float
    ) -> bool:
        raise NotImplementedError

    @staticmethod
    def _row_to_comment(r: sqlite3.Row) -> Comment:
        raise NotImplementedError

    def add_comment(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Comment:
        raise NotImplementedError

    def list_comments(
        self, parent_kind: str, parent_id: int, mentions: str | None = None
    ) -> list[Comment]:
        raise NotImplementedError

    def resolve_comment(
        self, cid: int, resolved: bool = True, actor: str = "human"
    ) -> Comment | None:
        raise NotImplementedError

    def restore_comment(
        self, parent_kind: str, parent_id: int, text: str, actor: str, ts: float, resolved: bool
    ) -> Comment | None:
        raise NotImplementedError

    def notes_map(self) -> dict[tuple[str, int], list[str]]:
        raise NotImplementedError

    def comments_map(self) -> dict[tuple[str, int], list[str]]:
        raise NotImplementedError

    def notes_full_map(self) -> dict[tuple[str, int], list[Note]]:
        raise NotImplementedError

    def comments_full_map(self) -> dict[tuple[str, int], list[Comment]]:
        raise NotImplementedError

    def issues_map(self) -> dict[tuple[str, int], list[str]]:
        raise NotImplementedError

    def update_task(
        self,
        tid: int,
        title: str | None = None,
        description: str | None = None,
        actor: str = "human",
    ) -> Task | None:
        raise NotImplementedError

    def set_blocked(
        self, tid: int, blocked: bool, reason: str = "", actor: str = "human"
    ) -> Task | None:
        raise NotImplementedError

    def gate_state(self, task_id: int) -> dict:
        raise NotImplementedError

    def branch_owners(
        self, repo_path: str, branch: str, remote: str = "", exclude_task: int = 0
    ) -> list[Task]:
        raise NotImplementedError

    def delete(self, kind: str, obj_id: int, actor: str = "human") -> bool:
        raise NotImplementedError

    @staticmethod
    def _delete_milestone_criteria(conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    @staticmethod
    def _delete_milestone_links(conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    def _delete_milestone_repos(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    @staticmethod
    def _delete_notes(conn: sqlite3.Connection, parent_kind: str, parent_id: int) -> None:
        raise NotImplementedError

    @staticmethod
    def _delete_comments(conn: sqlite3.Connection, parent_kind: str, parent_id: int) -> None:
        raise NotImplementedError

    def _delete_milestone_comments(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    def _delete_milestone_notes(self, conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    @staticmethod
    def _delete_milestone_forge_links(conn: sqlite3.Connection, milestone_id: int) -> None:
        raise NotImplementedError

    def _parent_exists(self, parent_kind: str, parent_id: int) -> bool:
        raise NotImplementedError

    def add_criteria(
        self, parent_kind: str, parent_id: int, text: str, actor: str = "human"
    ) -> Criterion:
        raise NotImplementedError

    @staticmethod
    def _row_to_criterion(r: sqlite3.Row) -> Criterion:
        raise NotImplementedError

    def get_criterion(self, cid: int) -> Criterion | None:
        raise NotImplementedError

    def relate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        raise NotImplementedError

    def unrelate_criterion(self, criterion_id: int, task_id: int, actor: str = "human") -> bool:
        raise NotImplementedError

    def criterion_tasks(self, criterion_id: int) -> list[Task]:
        raise NotImplementedError

    def task_criteria(self, task_id: int) -> list[Criterion]:
        raise NotImplementedError

    def all_criterion_links(self) -> list[dict]:
        raise NotImplementedError

    def list_criteria(self, parent_kind: str, parent_id: int) -> list[Criterion]:
        raise NotImplementedError

    def criteria_map(self) -> dict[tuple[str, int], list[Criterion]]:
        raise NotImplementedError

    def open_task_criteria_ids(self) -> set[int]:
        raise NotImplementedError

    def set_criteria(self, cid: int, done: bool, actor: str = "human") -> Criterion | None:
        raise NotImplementedError

    def delete_criteria(self, cid: int, actor: str = "human") -> bool:
        raise NotImplementedError

    def criteria_progress(self, parent_kind: str, parent_id: int) -> tuple[int, int]:
        raise NotImplementedError

    def open_criteria(self, kind: str, obj_id: int) -> list[Criterion]:
        raise NotImplementedError
