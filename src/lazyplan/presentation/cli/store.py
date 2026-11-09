"""Composition helpers that open the database for CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from ...infrastructure.repo import resolve_db_path
from ...store import Store


def optional_store(args: argparse.Namespace) -> Store | None:
    """Open an existing database without creating one."""
    path = Path(resolve_db_path(args.db)).expanduser()
    if not path.is_file():
        return None
    return Store(str(path))
