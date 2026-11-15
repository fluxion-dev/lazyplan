"""Store methods for the plan worktree registry."""

from __future__ import annotations

import sqlite3
import time

from ..core.entities import PlanWorktree
from .base import StoreBase


class WorktreesMixin(StoreBase):
    """Register, read, and remove checkouts per plan, repository, and lane."""

    def register_plan_worktree(
        self,
        plan_id: int,
        repo_path: str,
        worktree_path: str,
        branch: str = "",
        repo_remote: str = "",
        actor: str = "human",
        registered_at: float = 0.0,
        milestone_id: int | None = None,
    ) -> PlanWorktree:
        """Register or refresh one checkout; unique per plan, repo, and lane."""
        if self.get_plan(plan_id) is None:
            raise KeyError(f"plan #{plan_id} not found")
        repo = self.resolve_repo_path(repo_path)
        worktree = self.resolve_repo_path(worktree_path)
        if not repo.strip():
            raise ValueError("repo path must not be empty")
        if not worktree.strip():
            raise ValueError("worktree path must not be empty")
        if milestone_id is not None:
            self._check_lane(plan_id, milestone_id)
        stamp = registered_at if registered_at > 0 else time.time()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM plan_worktrees"
                " WHERE plan_id=? AND repo_path=? AND milestone_id IS ?",
                (plan_id, repo, milestone_id),
            ).fetchone()
            values = (
                repo_remote.strip(),
                worktree,
                branch.strip(),
                stamp,
                plan_id,
                repo,
                milestone_id,
            )
            if existing is None:
                conn.execute(
                    "INSERT INTO plan_worktrees"
                    " (plan_id, milestone_id, repo_path, repo_remote, worktree_path,"
                    " branch, registered_at)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (
                        plan_id,
                        milestone_id,
                        repo,
                        repo_remote.strip(),
                        worktree,
                        branch.strip(),
                        stamp,
                    ),
                )
            else:
                conn.execute(
                    "UPDATE plan_worktrees"
                    " SET repo_remote=?, worktree_path=?, branch=?, registered_at=?"
                    " WHERE plan_id=? AND repo_path=? AND milestone_id IS ?",
                    values,
                )
            row = conn.execute(
                "SELECT * FROM plan_worktrees"
                " WHERE plan_id=? AND repo_path=? AND milestone_id IS ?",
                (plan_id, repo, milestone_id),
            ).fetchone()
            assert row is not None
            worktree_row = self._row_to_plan_worktree(row)
        lane = f" lane M{milestone_id}" if milestone_id is not None else ""
        self.log(actor, "worktree", "register", f"plan #{plan_id}{lane}: {worktree}")
        return worktree_row

    def _check_lane(self, plan_id: int, milestone_id: int) -> None:
        """Refuse a lane that does not belong to the plan."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT plan_id FROM milestones WHERE id=?", (milestone_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"milestone #{milestone_id} not found")
        if int(row["plan_id"]) != plan_id:
            raise ValueError(f"milestone #{milestone_id} does not belong to plan #{plan_id}")

    def get_plan_worktree(
        self, plan_id: int, repo_path: str, milestone_id: int | None = None
    ) -> PlanWorktree | None:
        """The registered checkout for one plan, repo, and lane, or None."""
        repo = self.resolve_repo_path(repo_path)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM plan_worktrees"
                " WHERE plan_id=? AND repo_path=? AND milestone_id IS ?",
                (plan_id, repo, milestone_id),
            ).fetchone()
        return None if row is None else self._row_to_plan_worktree(row)

    def list_plan_worktrees(self, plan_id: int) -> list[PlanWorktree]:
        """Every registered checkout for one plan, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM plan_worktrees WHERE plan_id=? ORDER BY id",
                (plan_id,),
            ).fetchall()
        return [self._row_to_plan_worktree(row) for row in rows]

    def plan_worktrees_map(self) -> dict[int, list[PlanWorktree]]:
        """Every registration grouped by plan id, oldest first, in one read."""
        return self._grouped(
            "SELECT * FROM plan_worktrees ORDER BY id",
            (),
            self._row_to_plan_worktree,
            lambda row: int(row["plan_id"]),
        )

    def remove_plan_worktree(
        self,
        plan_id: int,
        repo_path: str,
        actor: str = "human",
        milestone_id: int | None = None,
    ) -> bool:
        """Remove one registration; False when the row was never registered."""
        repo = self.resolve_repo_path(repo_path)
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM plan_worktrees WHERE plan_id=? AND repo_path=? AND milestone_id IS ?",
                (plan_id, repo, milestone_id),
            )
            ok = (cur.rowcount or 0) > 0
        if ok:
            lane = f" lane M{milestone_id}" if milestone_id is not None else ""
            self.log(actor, "worktree", "remove", f"plan #{plan_id}{lane}: {repo}")
        return ok

    @staticmethod
    def _row_to_plan_worktree(row: sqlite3.Row) -> PlanWorktree:
        """Map one sqlite row to the entity."""
        keys = set(row.keys())
        raw_lane = row["milestone_id"] if "milestone_id" in keys else None
        return PlanWorktree(
            id=int(row["id"]),
            plan_id=int(row["plan_id"]),
            repo_path=str(row["repo_path"]),
            worktree_path=str(row["worktree_path"]),
            repo_remote=str(row["repo_remote"]),
            branch=str(row["branch"]),
            registered_at=float(row["registered_at"]),
            milestone_id=int(raw_lane) if raw_lane is not None else None,
        )
