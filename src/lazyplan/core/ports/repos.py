"""The repo-link port: checkouts linked to a plan, milestone, or task."""

from __future__ import annotations

from typing import Protocol

from .planning import PlanningPort


class ReposPort(PlanningPort, Protocol):
    """Repo link writes and the effective-repo inheritance read."""

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
