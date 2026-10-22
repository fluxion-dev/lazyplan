"""Database schema and migrations. Applied by Store on open; idempotent.

Stdlib only.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo',
    goal TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo'
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id INTEGER NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'todo',
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    text TEXT NOT NULL CHECK (trim(text) <> ''),
    done INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_criteria_parent ON criteria(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS vcs_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    sha TEXT NOT NULL CHECK (length(sha) = 40),
    subject TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    timestamp INTEGER NOT NULL DEFAULT 0,
    repo_root TEXT NOT NULL DEFAULT '',
    UNIQUE(parent_kind, parent_id, sha)
);
CREATE INDEX IF NOT EXISTS idx_vcs_links_parent ON vcs_links(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS entity_repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_kind TEXT NOT NULL CHECK (parent_kind IN ('plan', 'milestone', 'task')),
    parent_id INTEGER NOT NULL,
    repo_path TEXT NOT NULL,
    repo_remote TEXT NOT NULL DEFAULT '',
    UNIQUE(parent_kind, parent_id, repo_path, repo_remote)
);
CREATE INDEX IF NOT EXISTS idx_entity_repos_parent ON entity_repos(parent_kind, parent_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL DEFAULT 'human',
    kind TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_milestones_plan ON milestones(plan_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_events_id ON events(id);
"""

# Idempotent migrations for DBs created by older versions.
_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "plans": ("goal",),
}


def _migrate_elements(conn: sqlite3.Connection) -> None:
    """Rename pre-rename tables/kinds to plans/milestones, preserving data and ids.

    Old DBs (any version: with or without goal columns, with story|task-
    only or full criteria CHECKs, plus unrelated debris tables from older
    generations) are rebuilt to the current schema. Each element migrates
    independently, so a previously interrupted migration resumes cleanly.
    New DBs are untouched. The events log is history and is left as-is.
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


def migrate(conn: sqlite3.Connection) -> None:
    """Bring any DB to the current schema: migrate, create, backfill. Idempotent."""
    _migrate_elements(conn)
    conn.executescript(SCHEMA)
    _drop_priority_columns(conn)
    for table, cols in _MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col in cols:
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
