"""Maintenance persistence: database size, per-table bytes, and row counts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..core.ports.maintenance import MaintenanceReport, TableBytes
from .base import StoreBase


def _quoted(name: str) -> str:
    """Quote one SQLite identifier."""
    return '"' + name.replace('"', '""') + '"'


def _table_rows(conn: sqlite3.Connection, table: str) -> int:
    """Exact row count for one table."""
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {_quoted(table)}").fetchone()
    return int(row["count"] if row is not None else 0)


class MaintenanceMixin(StoreBase):
    """Maintenance reads and writes shared by the CLI, TUI, and MCP."""

    def _file_size(self) -> int:
        """Database file size in bytes, or zero when the file is gone."""
        try:
            return Path(self.path).expanduser().stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _dbstat_bytes(conn: sqlite3.Connection) -> dict[str, int]:
        """Page bytes per table and index from the dbstat virtual table."""
        rows = conn.execute(
            "SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name"
        ).fetchall()
        return {str(row["name"]): int(row["bytes"] or 0) for row in rows}

    @staticmethod
    def _schema_objects(
        conn: sqlite3.Connection,
    ) -> tuple[list[str], dict[str, list[str]], int]:
        """User tables, the indexes owned by each, and the schema row count."""
        rows = conn.execute("SELECT type, name, tbl_name FROM sqlite_master").fetchall()
        tables = [str(row["name"]) for row in rows if row["type"] == "table"]
        indexes: dict[str, list[str]] = {}
        for row in rows:
            if row["type"] == "index":
                indexes.setdefault(str(row["tbl_name"]), []).append(str(row["name"]))
        return tables, indexes, len(rows)

    def _table_sizes(
        self,
        conn: sqlite3.Connection,
        tables: list[str],
        indexes: dict[str, list[str]],
        page_bytes: dict[str, int],
    ) -> list[TableBytes]:
        """Attribute table and index pages to each table; schema pages stay separate."""
        rows: list[TableBytes] = []
        claimed: set[str] = set()
        for table in tables:
            names = [table, *indexes.get(table, ())]
            size = sum(page_bytes.get(name, 0) for name in names)
            claimed.update(names)
            rows.append(TableBytes(table, size, _table_rows(conn, table)))
        leftover = sum(size for name, size in page_bytes.items() if name not in claimed)
        if leftover:
            rows.append(TableBytes("sqlite_schema", leftover, 0))
        return rows

    def report(self) -> MaintenanceReport:
        """Per-table bytes and row counts, plus free and reclaimable pages."""
        with self._connect() as conn:
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
            tables, indexes, _schema_rows = self._schema_objects(conn)
            try:
                page_bytes = self._dbstat_bytes(conn)
                method = "dbstat"
            except sqlite3.OperationalError:
                page_bytes = {}
                method = "page_count"
            if method == "dbstat":
                sized = self._table_sizes(conn, tables, indexes, page_bytes)
                total_bytes = sum(row.bytes for row in sized)
            else:
                sized = [TableBytes(table, 0, _table_rows(conn, table)) for table in tables]
                total_bytes = page_count * page_size
        free_bytes = free_pages * page_size
        return MaintenanceReport(
            method=method,
            tables=tuple(sized),
            total_bytes=total_bytes,
            free_bytes=free_bytes,
            reclaimable_bytes=free_bytes,
        )
