"""Cached git branch/dirty state for previews and detail screens."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ...design import repo_project_name
from ...vcs import detect_backend

if TYPE_CHECKING:
    from ..app import LazyplanApp

CACHE_TTL = 30.0


class GitStateController:
    """Own the per-checkout git probe and its TTL cache."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app
        self.cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.pending: set[str] = set()

    @staticmethod
    def empty() -> dict[str, Any]:
        return {
            "branch": "",
            "dirty": False,
            "ahead": 0,
            "behind": 0,
            "upstream": "",
            "detached": False,
        }

    def state(self, path: str) -> dict[str, Any]:
        """Cached branch/dirty state; refresh in a worker when stale."""
        now = time.time()
        cached = self.cache.get(path)
        if cached is not None and now - cached[0] < CACHE_TTL:
            return cached[1]
        if path not in self.pending:
            self.pending.add(path)
            self.app.run_worker(lambda: self.load(path), thread=True, exclusive=False)
        return cached[1] if cached is not None else self.empty()

    def load(self, path: str) -> None:
        """Worker: probe one checkout without blocking the UI thread."""
        state = self.empty()
        backend, root = detect_backend(path)
        if backend is not None and root is not None:
            status = backend.status(root)
            state.update(
                {
                    "branch": status.branch,
                    "dirty": status.dirty,
                    "ahead": status.ahead,
                    "behind": status.behind,
                    "upstream": status.upstream,
                    "detached": status.detached,
                }
            )
        self.app.call_from_thread(self.store, path, state)

    def store(self, path: str, state: dict[str, Any]) -> None:
        self.pending.discard(path)
        self.cache[path] = (time.time(), state)
        if self.app._mounted and not self.app._refreshing:
            self.app.update_preview(force=True)

    def preview_bits(self, repos: list[dict[str, Any]]) -> list[str]:
        """Compact branch/dirty bits for the preview's linked checkouts."""
        bits: list[str] = []
        for repo in repos[:2]:
            path = str(repo.get("repo_path", "") or "")
            if not path:
                continue
            state = self.state(path)
            branch = state["branch"]
            if not branch:
                branch = "detached" if state["detached"] else "unknown"
            name = repo_project_name(repo) or path
            dirty = " dirty" if state["dirty"] else " clean"
            bits.append(f"{name} {branch}{dirty}")
        return bits
