"""The forge-link port: pull requests, issues, and branch ownership."""

from __future__ import annotations

from typing import Protocol

from ..entities import ForgeLink, Task


class ForgePort(Protocol):
    """Forge link writes and reads used by provenance, forge, and attribution."""

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

    def forge_counts_map(self) -> dict[tuple[str, int], tuple[int, int]]: ...

    def branch_owners(
        self, repo_path: str, branch: str, remote: str = "", exclude_task: int = 0
    ) -> list[Task]: ...
