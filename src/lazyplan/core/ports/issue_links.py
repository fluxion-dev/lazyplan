"""The issue-link port: provider issues attached to a row."""

from __future__ import annotations

from typing import Protocol


class IssueLinksPort(Protocol):
    """Provider issue links used by provenance, transfer, and the row views."""

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
    ) -> dict: ...

    def get_issue_link(self, provider: str, external_id: str) -> dict | None: ...

    def list_issue_links(self, row_kind: str, row_id: int) -> list[dict]: ...

    def update_issue_link(
        self, provider: str, external_id: str, title: str, url: str, state: str, updated_at: float
    ) -> bool: ...

    def issue_links_map(self) -> dict[tuple[str, int], list[dict]]: ...
