"""Cross-domain Store declarations for links, repos, and views."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..models import ForgeLink, Milestone, Plan, Status, Task, VcsLink


class StoreStubsLinks:
    """Declarations for link, repo, and view methods."""

    """Declarations for link, repo, and view methods."""

    @staticmethod
    def _row_to_link(r: sqlite3.Row) -> VcsLink:
        raise NotImplementedError

    def link_commit(
        self,
        parent_kind: str,
        parent_id: int,
        sha: str,
        subject: str = "",
        author: str = "",
        timestamp: int = 0,
        repo_root: str = "",
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink:
        raise NotImplementedError

    def update_link(
        self,
        link_id: int,
        *,
        subject: str,
        author: str,
        timestamp: int,
        repo_root: str,
        stale: bool,
        checked_at: int,
        files: tuple[str, ...] = (),
        actor: str = "human",
    ) -> VcsLink | None:
        raise NotImplementedError

    def unlink_commit(
        self, parent_kind: str, parent_id: int, sha: str, actor: str = "human"
    ) -> bool:
        raise NotImplementedError

    def list_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        raise NotImplementedError

    def links_for_sha(self, sha: str) -> list[VcsLink]:
        raise NotImplementedError

    @staticmethod
    def _row_to_forge_link(r: sqlite3.Row) -> ForgeLink:
        raise NotImplementedError

    def link_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        url: str = "",
        title: str = "",
        state: str = "",
        checks: str = "",
        reviews: str = "",
        author: str = "",
        base_ref: str = "",
        head_ref: str = "",
        merged_at: str = "",
        merge_commit_sha: str = "",
        updated_at: int = 0,
        stale: bool = False,
        payload: str = "",
        actor: str = "human",
    ) -> ForgeLink:
        raise NotImplementedError

    def unlink_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        actor: str = "human",
    ) -> bool:
        raise NotImplementedError

    def list_forge_links(self, parent_kind: str, parent_id: int, kind: str = "") -> list[ForgeLink]:
        raise NotImplementedError

    def effective_forge_links(
        self, parent_kind: str, parent_id: int, kind: str = ""
    ) -> list[ForgeLink]:
        raise NotImplementedError

    def forge_links_map(self) -> dict[tuple[str, int], list[ForgeLink]]:
        raise NotImplementedError

    def vcs_links_map(self) -> dict[tuple[str, int], list[VcsLink]]:
        raise NotImplementedError

    def cache_get(self, key: str) -> dict | None:
        raise NotImplementedError

    def cache_put(self, key: str, etag: str, fetched_at: int, payload: str) -> None:
        raise NotImplementedError

    def effective_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]:
        raise NotImplementedError

    @staticmethod
    def _norm_repo_path(path: str | Path) -> str:
        raise NotImplementedError

    def add_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str = "",
        branch: str = "",
        base_sha: str = "",
        actor: str = "human",
    ) -> dict:
        raise NotImplementedError

    def remove_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str | None = None,
        actor: str = "human",
    ) -> bool:
        raise NotImplementedError

    def list_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        raise NotImplementedError

    def effective_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        raise NotImplementedError

    def repos_map(self) -> dict[tuple[str, int], list[dict]]:
        raise NotImplementedError

    @staticmethod
    def _delete_entity_repos(conn: sqlite3.Connection, kind: str, obj_id: int) -> None:
        raise NotImplementedError

    def get_parent(self, kind: str, obj_id: int) -> Plan | Milestone | Task | None:
        raise NotImplementedError

    def _task_view(self, t: Task) -> dict:
        raise NotImplementedError

    def _task_show(self, t: Task) -> dict:
        raise NotImplementedError

    def _milestone_show(self, s: Milestone) -> dict:
        raise NotImplementedError

    def _plan_show(self, p: Plan) -> dict:
        raise NotImplementedError

    def get_full(self, kind: str, obj_id: int) -> dict | None:
        raise NotImplementedError

    def get_full_many(self, kind: str, obj_ids: list[int]) -> list[dict]:
        raise NotImplementedError

    def status_events(self, kind: str) -> list[tuple[float, str]]:
        raise NotImplementedError

    def plan_status_events_map(self) -> dict[int, tuple[float, str]]:
        raise NotImplementedError

    def set_status_raw(self, kind: str, obj_id: int, status: Status) -> bool:
        raise NotImplementedError

    def counts(self) -> dict[str, int]:
        raise NotImplementedError
