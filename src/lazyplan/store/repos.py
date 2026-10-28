"""Store methods for links."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..kinds import check_parent_kind
from .base import (
    StoreBase,
)


class ReposMixin(StoreBase):
    """Store methods for links."""

    @staticmethod
    def _norm_repo_path(path: str | Path) -> str:
        """Absolute normalized repo path (no existence requirement)."""
        p = Path(str(path)).expanduser()
        try:
            return str(p.resolve())
        except OSError:
            return str(p.absolute())

    def add_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str = "",
        branch: str = "",
        base_sha: str = "",
        actor: str = "human",
    ) -> dict:
        """Link a repo checkout to a row (idempotent on re-link)."""
        check_parent_kind(parent_kind)
        if not self._parent_exists(parent_kind, parent_id):
            raise KeyError(f"{parent_kind} #{parent_id} not found")
        norm_path = self._norm_repo_path(repo_path)
        if not norm_path.strip():
            raise ValueError("repo path must not be empty")
        remote = (repo_remote or "").strip()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO entity_repos"
                " (parent_kind, parent_id, repo_path, repo_remote, branch, base_sha)"
                " VALUES (?,?,?,?,?,?)",
                (parent_kind, parent_id, norm_path, remote, branch.strip(), base_sha.strip()),
            )
            if branch or base_sha:
                conn.execute(
                    "UPDATE entity_repos SET branch=?, base_sha=?"
                    " WHERE parent_kind=? AND parent_id=? AND repo_path=? AND repo_remote=?",
                    (
                        branch.strip(),
                        base_sha.strip(),
                        parent_kind,
                        parent_id,
                        norm_path,
                        remote,
                    ),
                )
            r = conn.execute(
                "SELECT * FROM entity_repos WHERE parent_kind=? AND parent_id=?"
                " AND repo_path=? AND repo_remote=?",
                (parent_kind, parent_id, norm_path, remote),
            ).fetchone()
            assert r is not None
            row = dict(r)
        self.log(actor, "repo", "link", f"{parent_kind} #{parent_id}: {norm_path}")
        return row

    def remove_repo_link(
        self,
        parent_kind: str,
        parent_id: int,
        repo_path: str,
        repo_remote: str | None = None,
        actor: str = "human",
    ) -> bool:
        """Unlink a repo; without remote, removes all remotes for the path."""
        check_parent_kind(parent_kind)
        norm_path = self._norm_repo_path(repo_path)
        with self._connect() as conn:
            if repo_remote is None:
                cur = conn.execute(
                    "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=? AND repo_path=?",
                    (parent_kind, parent_id, norm_path),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=?"
                    " AND repo_path=? AND repo_remote=?",
                    (parent_kind, parent_id, norm_path, (repo_remote or "").strip()),
                )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "repo", "unlink", f"{parent_kind} #{parent_id}: {norm_path}")
        return ok

    def list_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        """Explicit repo links on one row, oldest first."""
        check_parent_kind(parent_kind)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entity_repos WHERE parent_kind=? AND parent_id=? ORDER BY id",
                (parent_kind, parent_id),
            ).fetchall()
        return [dict(r) for r in rows]

    def effective_repos(self, parent_kind: str, parent_id: int) -> list[dict]:
        """Effective repos: explicit links, else inherited from parent plan."""
        check_parent_kind(parent_kind)
        explicit = self.list_repos(parent_kind, parent_id)
        if explicit:
            return explicit
        if parent_kind == "task":
            t = self.get_task(parent_id)
            if t is not None:
                return self.effective_repos("milestone", t.milestone_id)
        elif parent_kind == "milestone":
            s = self.get_milestone(parent_id)
            if s is not None:
                return self.list_repos("plan", s.plan_id)
        return []

    def repos_map(self) -> dict[tuple[str, int], list[dict]]:
        """Every linked repo grouped by (parent_kind, parent_id), oldest first."""
        with self._connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT id, parent_kind, parent_id, repo_path, repo_remote, branch, base_sha"
                    " FROM entity_repos ORDER BY id"
                ).fetchall()
            except Exception:
                return {}
        out: dict[tuple[str, int], list[dict]] = {}
        for r in rows:
            out.setdefault((r["parent_kind"], r["parent_id"]), []).append(dict(r))
        return out

    @staticmethod
    def _delete_entity_repos(conn: sqlite3.Connection, kind: str, obj_id: int) -> None:
        """Remove repo links on one row (callers handle subtree fan-out)."""
        try:
            conn.execute(
                "DELETE FROM entity_repos WHERE parent_kind=? AND parent_id=?", (kind, obj_id)
            )
        except Exception:
            pass
