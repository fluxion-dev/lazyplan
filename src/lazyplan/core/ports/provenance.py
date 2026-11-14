"""The provenance repository port: commits, repos, forge links, and gates."""

from __future__ import annotations

from typing import Protocol

from .collaboration import CollaborationPort
from .evidence import EvidencePort
from .forge import ForgePort
from .issue_links import IssueLinksPort
from .repos import ReposPort
from .touchpoints import TouchpointReadPort
from .vcs import VcsPort


class CachePort(Protocol):
    """Small ETag cache surface used by the GitHub client."""

    def cache_get(self, key: str) -> dict | None: ...

    def cache_put(self, key: str, etag: str, fetched_at: int, payload: str) -> None: ...


class ProvenancePort(
    ReposPort,
    CollaborationPort,
    CachePort,
    VcsPort,
    ForgePort,
    EvidencePort,
    IssueLinksPort,
    TouchpointReadPort,
    Protocol,
):
    """Commit, repo, forge, and task-gate surface composed from capabilities."""
