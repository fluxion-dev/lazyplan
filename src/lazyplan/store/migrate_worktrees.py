"""Lane column and partial unique indexes for the plan worktree registry."""

from __future__ import annotations

import sqlite3

_LANE_TABLE = """
CREATE TABLE plan_worktrees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    milestone_id INTEGER REFERENCES milestones(id) ON DELETE CASCADE,
    repo_path TEXT NOT NULL,
    repo_remote TEXT NOT NULL DEFAULT '',
    worktree_path TEXT NOT NULL,
    branch TEXT NOT NULL DEFAULT '',
    registered_at REAL NOT NULL
)
"""


def migrate_worktree_lanes(conn: sqlite3.Connection) -> None:
    """Allow one worktree per lane while keeping the plan-level row unique."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(plan_worktrees)").fetchall()}
    if "milestone_id" not in columns:
        conn.execute("ALTER TABLE plan_worktrees RENAME TO plan_worktrees_old")
        conn.execute(_LANE_TABLE)
        conn.execute(
            "INSERT INTO plan_worktrees"
            " (id, plan_id, milestone_id, repo_path, repo_remote, worktree_path,"
            " branch, registered_at)"
            " SELECT id, plan_id, NULL, repo_path, repo_remote, worktree_path,"
            " branch, registered_at FROM plan_worktrees_old"
        )
        conn.execute("DROP TABLE plan_worktrees_old")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_plan_worktrees_plan_repo"
        " ON plan_worktrees(plan_id, repo_path) WHERE milestone_id IS NULL"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_plan_worktrees_lane"
        " ON plan_worktrees(plan_id, milestone_id, repo_path) WHERE milestone_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plan_worktrees_milestone ON plan_worktrees(milestone_id)"
    )
