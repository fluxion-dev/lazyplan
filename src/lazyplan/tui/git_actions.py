"""Git status, commit refresh, capture, and pull-request actions."""

from __future__ import annotations

import webbrowser
from typing import Any

from .. import services
from ..render import render_git_status
from .base import AppBase
from .screens.source import SourceScreen


class GitActionMixin(AppBase):
    """Read-only git actions and the source trail entry point."""

    def _git_refresh_done(self, result: dict[str, Any]) -> None:
        self.notify(
            f"checked {result['checked']} links · "
            f"{result['updated']} updated · {result['stale']} stale",
            timeout=6,
        )
        self._saved("git links refreshed")

    def action_git_status(self) -> None:
        """Show branch and dirty state for the selected row's checkouts."""
        selected = self._git_selection()
        if selected is None:
            return
        kind, oid = selected
        self.notify("reading git status…", timeout=2)
        self.run_worker(
            lambda: self._git_status_worker(kind, oid),
            thread=True,
            exclusive=True,
        )

    def action_git_refresh(self) -> None:
        """Re-resolve cached commits and mark stale links."""
        selected = self._git_selection()
        if selected is None:
            return
        kind, oid = selected
        self.notify("refreshing commit links…", timeout=2)
        self.run_worker(
            lambda: self._git_refresh_worker(kind, oid),
            thread=True,
            exclusive=True,
        )

    def _git_status_worker(self, kind: str, oid: int) -> None:
        try:
            entries = services.repo_statuses(self.store, kind, oid)
        except ValueError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error", timeout=5)
            return
        self.call_from_thread(self._git_status_done, entries)

    def action_open_pr(self) -> None:
        """Open the first linked pull request in the default browser."""
        selected = self._git_selection()
        if selected is None:
            return
        kind, oid = selected
        links = self.store.effective_forge_links(kind, oid)
        url = next((link.url for link in links if link.url), "")
        if not url:
            self.notify("no pull request linked", timeout=3)
            return
        webbrowser.open(url)
        self.notify(f"opened {url}", timeout=4)

    def _git_refresh_worker(self, kind: str, oid: int) -> None:
        try:
            result = services.refresh_links(self.store, kind, oid)
        except Exception as exc:
            self.call_from_thread(
                self.notify, f"refresh failed: {exc}", severity="error", timeout=5
            )
            return
        self.call_from_thread(self._git_refresh_done, result)

    def action_source_trail(self) -> None:
        """Open the read-only source trail for the selected row."""
        selected = self._git_selection()
        if selected is None:
            return
        kind, oid = selected
        self.push_screen(SourceScreen(self.store, kind, oid))

    def action_git_capture(self) -> None:
        """Link a safe current HEAD to the selected row."""
        selected = self._git_selection()
        if selected is None:
            return
        kind, oid = selected
        before = {link.sha for link in self.store.list_links(kind, oid)}
        repos = self.store.effective_repos(kind, oid)
        cwd = str(repos[0]["repo_path"]) if repos else "."
        reason = services.auto_capture_head(self.store, kind, oid, cwd=cwd)
        after = {link.sha for link in self.store.list_links(kind, oid)}
        if after - before:
            self.notify("HEAD linked", timeout=4)
            self._saved("commit linked")
            return
        if reason:
            self.notify(f"not linked: {reason}", severity="warning", timeout=6)
            return
        self.notify("HEAD is already linked or unavailable", timeout=4)

    def _git_status_done(self, entries: list[dict[str, Any]]) -> None:
        if not entries:
            self.notify("no linked repos", timeout=3)
            return
        self.notify(render_git_status(entries), timeout=8)
        self._pending_note = "git status"

    def _git_selection(self) -> tuple[str, int] | None:
        """Selected row for a git action, or a notification when none."""
        if self.selected is None:
            self.notify("select a row first", timeout=3)
            return None
        return self.selected
