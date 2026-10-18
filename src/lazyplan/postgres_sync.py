"""Postgres sync adapter (S#5): one-way snapshot SQLite -> Postgres replica.

The replica exists so dashboards, SQL-savvy agents, and multi-machine readers
can query the plan without touching the live SQLite file. SQLite stays the
source of truth; `lpui sync` overwrites replica tables wholesale.

Requires: pip install "lazyplan[postgres]"  (psycopg v3)
"""

from __future__ import annotations

import sqlite3
from typing import Any

TABLES = (
    "projects",
    "stories",
    "tasks",
    "links",
    "criteria",
    "risks",
    "milestones",
    "proposals",
    "questions",
    "events",
)

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
    goal TEXT NOT NULL DEFAULT '', success_metrics TEXT NOT NULL DEFAULT '',
    scope_in TEXT NOT NULL DEFAULT '', scope_out TEXT NOT NULL DEFAULT '',
    assumptions TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'todo',
    start_date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '', estimate TEXT NOT NULL DEFAULT '',
    blocked_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY, story_id INTEGER NOT NULL, title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo', estimate TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '', end_date TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '',
    blocked_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY, parent_kind TEXT NOT NULL DEFAULT '',
    parent_id INTEGER NOT NULL DEFAULT 0, url TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS criteria (
    id INTEGER PRIMARY KEY, parent_kind TEXT NOT NULL DEFAULT '',
    parent_id INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS risks (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '', likelihood TEXT NOT NULL DEFAULT 'med',
    impact TEXT NOT NULL DEFAULT 'med', mitigation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS milestones (
    id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '', date TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL DEFAULT '',
    parent_id INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    result_id INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY, actor TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '', answer TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open', ts REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL DEFAULT 0,
    actor TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT ''
);
"""


def _psycopg() -> Any:
    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise RuntimeError('Postgres sync needs psycopg: pip install "lazyplan[postgres]"') from exc
    return psycopg


def sync_sqlite_to_pg(sqlite_path: str, dsn: str) -> dict[str, int]:
    """Overwrite replica tables from the SQLite file. Returns per-table counts."""
    psycopg = _psycopg()
    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, autocommit=True) as dst:
        with dst.cursor() as cur:
            cur.execute(PG_SCHEMA)
            for table in TABLES:
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
                cols = [d["name"] for d in src.execute(f"PRAGMA table_info({table})").fetchall()]
                cur.execute(f"DELETE FROM {table}")
                if rows:
                    ph = ",".join(["%s"] * len(cols))
                    cur.executemany(
                        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph})",
                        [tuple(r[c] for c in cols) for r in rows],
                    )
                counts[table] = len(rows)
    src.close()
    return counts
