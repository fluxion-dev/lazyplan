"""The checkout path port used by store and service use cases."""

from __future__ import annotations

from typing import Protocol


class PathPort(Protocol):
    """Checkout and repo path resolution without importing infrastructure."""

    def repo_root(self, cwd: str = ".") -> str | None: ...

    def checkout_path(self, cwd: str | None = None) -> str: ...

    def resolve_repo_path(self, path: str) -> str: ...

    def normalize_repo_path(self, path: str) -> str: ...
