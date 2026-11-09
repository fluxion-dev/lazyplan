"""Checkout path resolution and the default path adapter."""

from __future__ import annotations

from pathlib import Path

from .repo import find_repo_root
from .repo_paths import normalize_repo_path, resolve_repo_path


def checkout_path(cwd: str | Path | None = None) -> str:
    """Repo root for *cwd*, else the resolved working directory."""
    base = Path.cwd() if cwd is None else Path(cwd)
    root = find_repo_root(base)
    try:
        return str(Path(root).resolve() if root is not None else base.resolve())
    except OSError:
        return str(base.absolute())


class PathAdapter:
    """Default PathPort implementation backed by the repo helpers."""

    def repo_root(self, cwd: str = ".") -> str | None:
        """Enclosing git root for *cwd*, or None."""
        root = find_repo_root(cwd)
        return None if root is None else str(root)

    def checkout_path(self, cwd: str | None = None) -> str:
        """Repo root for *cwd*, else the resolved working directory."""
        return str(checkout_path(cwd))

    def resolve_repo_path(self, path: str) -> str:
        """Absolute path without case folding."""
        return resolve_repo_path(path)

    def normalize_repo_path(self, path: str) -> str:
        """Absolute, case-folded path for equality checks."""
        return normalize_repo_path(path)
