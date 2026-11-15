"""Lane columns added to plans, milestones, and tasks after they shipped."""

from __future__ import annotations

import sqlite3

_ADDITIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "plans": (
        ("dispatch_mode", "TEXT NOT NULL DEFAULT 'serial'"),
        ("max_agents", "INTEGER NOT NULL DEFAULT 1"),
    ),
    "milestones": (
        ("lane_group", "INTEGER NOT NULL DEFAULT 1"),
        ("agent_role", "TEXT NOT NULL DEFAULT 'implementer'"),
    ),
    "tasks": (("role", "TEXT NOT NULL DEFAULT 'implementer'"),),
}


def migrate_lanes(conn: sqlite3.Connection) -> None:
    """Add dispatch, wave, and role columns to rows created before lanes."""
    for table, columns in _ADDITIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
