"""Store methods for the plan worktree registry."""

from __future__ import annotations

import sqlite3
import time

from ..core.entities import PlanWorktree
from .base import StoreBase


class WorktreesMixin(StoreBase):
    """Register, read, and remove one checkout per plan and repository."""

    def register_plan_worktree(
        self,
        plan_id: int,
        repo_path: str,
        worktree_path: str,
        branch: str = "",
        repo_remote: str = "",
        actor: str = "human",
        registered_at: float = 0.0,
    ) -> PlanWorktree:
        """Register or refresh one plan worktree; unique per plan and repo."""
        if self.get_plan(plan_id) is None:
            raise KeyError(f"plan #{plan_id} not found")
        repo = self.resolve_repo_path(repo_path)
        worktree = self.resolve_repo_path(worktree_path)
        if not repo.strip():
            raise ValueError("repo path must not be empty")
        if not worktree.strip():
            raise ValueError("worktree path must not be empty")
        stamp = registered_at if registered_at > 0 else time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO plan_worktrees"
                " (plan_id, repo_path, repo_remote, worktree_path, branch, registered_at)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(plan_id, repo_path) DO UPDATE SET"
                " repo_remote=excluded.repo_remote,"
                " worktree_path=excluded.worktree_path,"
                " branch=excluded.branch,"
                " registered_at=excluded.registered_at",
                (plan_id, repo, repo_remote.strip(), worktree, branch.strip(), stamp),
            )
            row = conn.execute(
                "SELECT * FROM plan_worktrees WHERE plan_id=? AND repo_path=?",
                (plan_id, repo),
            ).fetchone()
            assert row is not None
            worktree_row = self._row_to_plan_worktree(row)
        self.log(actor, "worktree", "register", f"plan #{plan_id}: {worktree}")
        return worktree_row

    def get_plan_worktree(self, plan_id: int, repo_path: str) -> PlanWorktree | None:
        """The registered worktree for one plan and repo, or None."""
        repo = self.resolve_repo_path(repo_path)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plan_worktrees WHERE plan_id=? AND repo_path=?",
                (plan_id, repo),
            ).fetchone()
        return None if row is None else self._row_to_plan_worktree(row)

    def list_plan_worktrees(self, plan_id: int) -> list[PlanWorktree]:
        """Every registered worktree for one plan, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plan_worktrees WHERE plan_id=? ORDER BY id",
                (plan_id,),
            ).fetchall()
        return [self._row_to_plan_worktree(row) for row in rows]

    def remove_plan_worktree(self, plan_id: int, repo_path: str, actor: str = "human") -> bool:
        """Remove one registration; False when the pair was never registered."""
        repo = self.resolve_repo_path(repo_path)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM plan_worktrees WHERE plan_id=? AND repo_path=?",
                (plan_id, repo),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            self.log(actor, "worktree", "remove", f"plan #{plan_id}: {repo}")
        return ok

    @staticmethod
    def _row_to_plan_worktree(row: sqlite3.Row) -> PlanWorktree:
        """Map one sqlite row to the entity."""
        return PlanWorktree(
            id=int(row["id"]),
            plan_id=int(row["plan_id"]),
            repo_path=str(row["repo_path"]),
            worktree_path=str(row["worktree_path"]),
            repo_remote=str(row["repo_remote"]),
            branch=str(row["branch"]),
            registered_at=float(row["registered_at"]),
        )
