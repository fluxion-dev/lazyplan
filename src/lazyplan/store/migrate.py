"""Database schema and migrations. Applied by Store on open; idempotent."""

from __future__ import annotations

import sqlite3
import uuid

from .migrate_lanes import migrate_lanes
from .migrate_worktrees import migrate_worktree_lanes
from .schema import SCHEMA

SCHEMA_VERSION = 19

# Idempotent migrations for DBs created by older versions.
_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "plans": ("goal",),
}


def _migrate_elements(conn: sqlite3.Connection) -> None:
    """Rename pre-rename tables/kinds to plans/milestones, preserving data and ids.

    Old DBs (any version: with or without goal columns, with story|task-only or
    full criteria CHECKs, plus unrelated debris) are rebuilt to the current schema;
    each element migrates independently, so an interrupted migration resumes
    cleanly. New DBs are untouched. The events log is history and is left as-is.
    """
    tables = {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

    def has(name: str) -> bool:
        return name in tables

    def columns(table: str) -> set[str]:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    migrated = False
    if "plans" not in tables and "projects" in tables:
        conn.execute("ALTER TABLE projects RENAME TO plans")
        tables.discard("projects")
        tables.add("plans")
        migrated = True
    # Ancient debris: very old generations left an unrelated `milestones`
    # table behind. Drop it only when provably empty and not ours; a
    # non-empty one means manual review, never guessing.
    if has("milestones") and "plan_id" not in columns("milestones"):
        count = conn.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]
        if count:
            raise RuntimeError(
                "found a non-empty legacy `milestones` table; carry data over with "
                "`lpui export --format json` + `lpui import --file`"
            )
        conn.execute("DROP TABLE milestones")
        tables.discard("milestones")
    if "milestones" not in tables and "stories" in tables:
        conn.execute("ALTER TABLE stories RENAME TO milestones")
        tables.discard("stories")
        tables.add("milestones")
        migrated = True
    if has("milestones") and "project_id" in columns("milestones"):
        conn.execute("ALTER TABLE milestones RENAME COLUMN project_id TO plan_id")
        migrated = True
    if has("tasks") and "story_id" in columns("tasks"):
        conn.execute("ALTER TABLE tasks RENAME COLUMN story_id TO milestone_id")
        migrated = True
    if not migrated:
        return
    # Refresh CHECK constraints (old tables pinned the old kind values),
    # remapping stored kinds while copying.
    remap = (
        "CASE parent_kind WHEN 'project' THEN 'plan'"
        " WHEN 'story' THEN 'milestone' ELSE parent_kind END"
    )
    if has("criteria"):
        conn.execute("ALTER TABLE criteria RENAME TO criteria_old")
        conn.execute(
            """
            CREATE TABLE criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
                parent_id INTEGER NOT NULL,
                text TEXT NOT NULL CHECK (trim(text) <> ''),
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO criteria (id, parent_kind, parent_id, text, done)"
            f" SELECT id, {remap}, parent_id, text, done FROM criteria_old"
        )
        conn.execute("DROP TABLE criteria_old")
    if has("vcs_links"):
        conn.execute("ALTER TABLE vcs_links RENAME TO vcs_links_old")
        conn.execute(
            """
            CREATE TABLE vcs_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
                parent_id INTEGER NOT NULL,
                sha TEXT NOT NULL CHECK (length(sha) = 40),
                subject TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                timestamp INTEGER NOT NULL DEFAULT 0,
                repo_root TEXT NOT NULL DEFAULT '',
                stale INTEGER NOT NULL DEFAULT 0,
                checked_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(parent_kind, parent_id, sha)
            )
            """
        )
        conn.execute(
            "INSERT INTO vcs_links"
            " (id, parent_kind, parent_id, sha, subject, author, timestamp, repo_root)"
            f" SELECT id, {remap}, parent_id, sha, subject, author, timestamp, repo_root"
            " FROM vcs_links_old"
        )
        conn.execute("DROP TABLE vcs_links_old")
    conn.execute("DROP INDEX IF EXISTS idx_stories_project")
    conn.execute("DROP INDEX IF EXISTS idx_tasks_story")
    # Remaining indexes are (re)created by SCHEMA in migrate() right after.


def _drop_priority_columns(conn: sqlite3.Connection) -> None:
    """Retire priority: drop the column from every element table when present."""
    for table in ("plans", "milestones", "tasks"):
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "priority" in existing:
            conn.execute(f"ALTER TABLE {table} DROP COLUMN priority")


def _migrate_vcs_link_state(conn: sqlite3.Connection) -> None:
    """Add refresh state and changed-file columns to vcs_links when missing."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(vcs_links)").fetchall()}
    if "stale" not in existing:
        conn.execute("ALTER TABLE vcs_links ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")
    if "checked_at" not in existing:
        conn.execute("ALTER TABLE vcs_links ADD COLUMN checked_at INTEGER NOT NULL DEFAULT 0")
    if "files" not in existing:
        conn.execute("ALTER TABLE vcs_links ADD COLUMN files TEXT NOT NULL DEFAULT '[]'")


def _migrate_entity_repo_branch(conn: sqlite3.Connection) -> None:
    """Add recorded branch/base columns to entity_repos when missing."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(entity_repos)").fetchall()}
    if "branch" not in existing:
        conn.execute("ALTER TABLE entity_repos ADD COLUMN branch TEXT NOT NULL DEFAULT ''")
    if "base_sha" not in existing:
        conn.execute("ALTER TABLE entity_repos ADD COLUMN base_sha TEXT NOT NULL DEFAULT ''")


def _migrate_forge_link_fields(conn: sqlite3.Connection) -> None:
    """Add review, merge, and stale columns to forge_links when missing."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(forge_links)").fetchall()}
    if "reviews" not in existing:
        conn.execute("ALTER TABLE forge_links ADD COLUMN reviews TEXT NOT NULL DEFAULT ''")
    if "stale" not in existing:
        conn.execute("ALTER TABLE forge_links ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")
    for col in ("base_ref", "head_ref", "merged_at", "merge_commit_sha"):
        if col not in existing:
            conn.execute(f"ALTER TABLE forge_links ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")


def _migrate_plan_uid(conn: sqlite3.Connection) -> None:
    """Add stable plan uids and backfill existing rows."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(plans)").fetchall()}
    if "uid" not in existing:
        conn.execute("ALTER TABLE plans ADD COLUMN uid TEXT NOT NULL DEFAULT ''")
    rows = conn.execute("SELECT id FROM plans WHERE uid = ''").fetchall()
    for row in rows:
        conn.execute("UPDATE plans SET uid=? WHERE id=?", (str(uuid.uuid4()), row["id"]))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_plans_uid ON plans(uid)")


def _migrate_task_blocked(conn: sqlite3.Connection) -> None:
    """Add the blocked flag to task tables created before it existed."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "blocked" not in existing:
        conn.execute("ALTER TABLE tasks ADD COLUMN blocked INTEGER NOT NULL DEFAULT 0")
    if "blocked_reason" not in existing:
        conn.execute("ALTER TABLE tasks ADD COLUMN blocked_reason TEXT NOT NULL DEFAULT ''")


def _migrate_events_session(conn: sqlite3.Connection) -> None:
    """Add the session tag to events and index it when missing."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    if "session_id" not in existing:
        conn.execute("ALTER TABLE events ADD COLUMN session_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id)")


def _tables(conn: sqlite3.Connection) -> set[str]:
    """Every table currently in the database."""
    return {
        str(r["name"])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _history_table(conn: sqlite3.Connection) -> str | None:
    """The session history table, under either its old or current name."""
    tables = _tables(conn)
    if "session_history" in tables:
        return "session_history"
    if "sessions" in tables:
        return "sessions"
    return None


def _migrate_session_history(conn: sqlite3.Connection) -> None:
    """Rename sessions to session_history, keeping every id and summary."""
    tables = _tables(conn)
    if "session_history" in tables and "sessions" not in tables:
        return
    if "sessions" in tables and "session_history" not in tables:
        conn.execute("ALTER TABLE sessions RENAME TO session_history")
        return
    if "sessions" in tables and "session_history" in tables:
        conn.execute("INSERT OR IGNORE INTO session_history SELECT * FROM sessions")
        conn.execute("DROP TABLE sessions")


def _migrate_session_state(conn: sqlite3.Connection) -> None:
    """Add lifecycle state to session history and backfill the heartbeat."""
    table = _history_table(conn)
    if table is None:
        return
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "phase" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN phase TEXT NOT NULL DEFAULT 'working'")
    if "last_seen_at" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN last_seen_at REAL NOT NULL DEFAULT 0")
    if "host" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN host TEXT NOT NULL DEFAULT ''")
    if "host_session" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN host_session TEXT NOT NULL DEFAULT ''")
    if "auto_closed" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN auto_closed INTEGER NOT NULL DEFAULT 0")
    conn.execute(f"UPDATE {table} SET last_seen_at=started_at WHERE last_seen_at=0")


def _migrate_session_attribution(conn: sqlite3.Connection) -> None:
    """Add how a session got its plan when the column is missing."""
    table = _history_table(conn)
    if table is None:
        return
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "plan_source" not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN plan_source TEXT NOT NULL DEFAULT 'auto'")


def _migrate_claim_location(conn: sqlite3.Connection) -> None:
    """Add the worktree and repo-root columns to claims when missing."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(task_claims)").fetchall()}
    if "worktree" not in existing:
        conn.execute("ALTER TABLE task_claims ADD COLUMN worktree TEXT NOT NULL DEFAULT ''")
    if "repo_path" not in existing:
        conn.execute("ALTER TABLE task_claims ADD COLUMN repo_path TEXT NOT NULL DEFAULT ''")


def _migrate_plan_worktree_required(conn: sqlite3.Connection) -> None:
    """Add the isolation flag to plans created before it existed."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(plans)").fetchall()}
    if "worktree_required" not in existing:
        conn.execute("ALTER TABLE plans ADD COLUMN worktree_required INTEGER NOT NULL DEFAULT 0")


def _migrate_archive_columns(conn: sqlite3.Connection) -> None:
    """Add the archive stamp to plans and session history, then index it."""
    history = _history_table(conn)
    tables = ["plans"] + ([history] if history else [])
    for table in tables:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "archived_at" not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN archived_at REAL NOT NULL DEFAULT 0")
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_archived ON {table}(archived_at)")


def _drop_agent_registry(conn: sqlite3.Connection) -> None:
    """Claims record who works on what; the agent registry tables go."""
    conn.execute("DROP TABLE IF EXISTS agent_events")
    conn.execute("DROP TABLE IF EXISTS agents")


def migrate(conn: sqlite3.Connection) -> None:
    """Bring any DB to the current schema: migrate, create, backfill. Idempotent."""
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current == SCHEMA_VERSION:
        return
    _migrate_elements(conn)
    _migrate_session_history(conn)
    conn.executescript(SCHEMA)
    migrate_worktree_lanes(conn)
    _migrate_plan_uid(conn)
    _migrate_task_blocked(conn)
    _migrate_events_session(conn)
    _migrate_session_state(conn)
    _migrate_session_attribution(conn)
    _migrate_claim_location(conn)
    _migrate_plan_worktree_required(conn)
    migrate_lanes(conn)
    _migrate_archive_columns(conn)
    _drop_agent_registry(conn)
    _drop_priority_columns(conn)
    _migrate_vcs_link_state(conn)
    _migrate_entity_repo_branch(conn)
    _migrate_forge_link_fields(conn)
    for table, cols in _MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in cols:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
