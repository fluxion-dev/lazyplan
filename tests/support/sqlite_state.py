"""Quiesce SQLite before a test snapshots a directory tree."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def quiesce(root: Path) -> None:
    """Checkpoint every database under *root* so transient journals settle."""
    try:
        databases = sorted(root.rglob("*.db"))
    except OSError:
        return
    for path in databases:
        try:
            connection = sqlite3.connect(str(path), timeout=1.0)
        except sqlite3.Error:
            continue
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        finally:
            connection.close()
