"""The provenance repository port: commits, repos, forge links, and gates."""

from __future__ import annotations

from typing import Protocol

from ..entities import CriterionEvidence, ForgeLink, Task, VcsLink
from .collaboration import CollaborationPort


class CachePort(Protocol):
    """Small ETag cache surface used by the GitHub client."""

    def cache_get(self, key: str) -> dict | None: ...

    def cache_put(self, key: str, etag: str, fetched_at: int, payload: str) -> None: ...


class ProvenancePort(CollaborationPort, CachePort, Protocol):
    """Commit, repo, forge, and task-gate surface used by provenance services."""

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
    ) -> VcsLink: ...

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
    ) -> VcsLink | None: ...

    def unlink_commit(
        self, parent_kind: str, parent_id: int, sha: str, actor: str = "human"
    ) -> bool: ...

    def list_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]: ...

    def effective_links(self, parent_kind: str, parent_id: int) -> list[VcsLink]: ...

    def links_for_sha(self, sha: str) -> list[VcsLink]: ...

    def vcs_links_map(self) -> dict[tuple[str, int], list[VcsLink]]: ...

    def add_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str = "",
        branch: str = "",
        base_sha: str = "",
        actor: str = "human",
    ) -> dict: ...

    def remove_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str | None = None,
        actor: str = "human",
    ) -> bool: ...

    def list_repos(self, parent_kind: str, parent_id: int) -> list[dict]: ...

    def effective_repos(self, parent_kind: str, parent_id: int) -> list[dict]: ...

    def repos_map(self) -> dict[tuple[str, int], list[dict]]: ...

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
    ) -> ForgeLink: ...

    def unlink_forge(
        self,
        parent_kind: str,
        parent_id: int,
        number: int,
        *,
        provider: str = "github",
        kind: str = "pull",
        actor: str = "human",
    ) -> bool: ...

    def list_forge_links(
        self, parent_kind: str, parent_id: int, kind: str = ""
    ) -> list[ForgeLink]: ...

    def effective_forge_links(
        self, parent_kind: str, parent_id: int, kind: str = ""
    ) -> list[ForgeLink]: ...

    def forge_links_map(self) -> dict[tuple[str, int], list[ForgeLink]]: ...

    def branch_owners(
        self, repo_path: str, branch: str, remote: str = "", exclude_task: int = 0
    ) -> list[Task]: ...

    def gate_state(self, task_id: int) -> dict: ...

    def criterion_tasks(self, criterion_id: int) -> list[Task]: ...

    def list_issue_links(self, parent_kind: str, parent_id: int) -> list[dict]: ...

    def add_evidence(
        self,
        criterion_id: int,
        command: str = "",
        exit_code: int | None = None,
        commit_sha: str = "",
        pr_url: str = "",
        artifact_path: str = "",
        note: str = "",
        task_id: int | None = None,
        actor: str = "human",
    ) -> CriterionEvidence: ...

    def list_evidence(self, criterion_id: int) -> list[CriterionEvidence]: ...

    def evidence_map(self) -> dict[int, list[CriterionEvidence]]: ...
