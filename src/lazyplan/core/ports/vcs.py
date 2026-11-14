"""The commit-link port: rows linked to git commits."""

from __future__ import annotations

from typing import Protocol

from ..entities import VcsLink


class VcsPort(Protocol):
    """Commit link writes and reads used by provenance and review."""

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
