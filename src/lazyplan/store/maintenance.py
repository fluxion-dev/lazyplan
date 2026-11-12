"""Maintenance persistence: database size, per-table bytes, row counts, and trim."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import MaintenanceBusy
from ..core.policies.maintenance import DEFAULT_WINDOW_SECS, event_cutoff
from ..core.ports.maintenance import (
    MaintenanceReport,
    TableBytes,
    TableCount,
    TrimResult,
    VacuumResult,
)
from .base import StoreBase


@dataclass(frozen=True)
class TrimTarget:
    """One table and predicate whose derived rows trim may delete."""

    table: str
    where: str
    params: tuple[object, ...] = ()


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

    @staticmethod
    def _trim_targets(now: float, cutoff: float) -> tuple[TrimTarget, ...]:
        """Every derived-row delete trim may make, in a safe order."""
        missing_parent = (
            "(parent_kind='plan' AND NOT EXISTS (SELECT 1 FROM plans WHERE id=parent_id))"
            " OR (parent_kind='milestone'"
            " AND NOT EXISTS (SELECT 1 FROM milestones WHERE id=parent_id))"
            " OR (parent_kind='task' AND NOT EXISTS (SELECT 1 FROM tasks WHERE id=parent_id))"
        )
        return (
            TrimTarget(
                "task_touchpoints",
                "task_id IN (SELECT task_id FROM task_claims WHERE expires_at <= ?)",
                (now,),
            ),
            TrimTarget("task_claims", "expires_at <= ?", (now,)),
            TrimTarget("forge_cache", "fetched_at < ?", (cutoff,)),
            TrimTarget(
                "forge_links",
                "lower(state) IN ('closed', 'merged') OR merged_at <> ''",
            ),
            TrimTarget(
                "criterion_links",
                "NOT EXISTS (SELECT 1 FROM criteria c WHERE c.id=criterion_id)"
                " OR NOT EXISTS (SELECT 1 FROM tasks t WHERE t.id=task_id)",
            ),
            TrimTarget(
                "criterion_evidence",
                "NOT EXISTS (SELECT 1 FROM criteria c WHERE c.id=criterion_id)"
                " OR (task_id IS NOT NULL"
                " AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.id=task_id))",
            ),
            TrimTarget("criteria", missing_parent),
            TrimTarget("notes", missing_parent),
            TrimTarget("comments", missing_parent),
            TrimTarget(
                "entity_keys",
                "(kind='plan' AND NOT EXISTS (SELECT 1 FROM plans WHERE id=row_id))"
                " OR (kind='milestone'"
                " AND NOT EXISTS (SELECT 1 FROM milestones WHERE id=row_id))"
                " OR (kind='task' AND NOT EXISTS (SELECT 1 FROM tasks WHERE id=row_id))",
            ),
            TrimTarget("entity_repos", missing_parent),
            TrimTarget(
                "issue_links",
                "(row_kind='plan' AND NOT EXISTS (SELECT 1 FROM plans WHERE id=row_id))"
                " OR (row_kind='milestone'"
                " AND NOT EXISTS (SELECT 1 FROM milestones WHERE id=row_id))"
                " OR (row_kind='task' AND NOT EXISTS (SELECT 1 FROM tasks WHERE id=row_id))",
            ),
            TrimTarget("vcs_links", missing_parent),
            TrimTarget("events", "ts < ?", (cutoff,)),
        )

    @staticmethod
    def _count_target(conn: sqlite3.Connection, target: TrimTarget) -> int:
        """Rows one trim target currently matches."""
        row = conn.execute(
            f"SELECT COUNT(*) AS count FROM {_quoted(target.table)} WHERE {target.where}",
            target.params,
        ).fetchone()
        return int(row["count"] if row is not None else 0)

    def _trim_counts(
        self, conn: sqlite3.Connection, now: float, window_secs: float
    ) -> dict[str, int]:
        """Candidate counts per table, shared by report and trim."""
        cutoff = event_cutoff(now, window_secs)
        return {
            target.table: self._count_target(conn, target)
            for target in self._trim_targets(now, cutoff)
        }

    def report(self) -> MaintenanceReport:
        """Per-table bytes and row counts, plus free and reclaimable pages."""
        now = time.time()
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
            dead_counts = self._trim_counts(conn, now, DEFAULT_WINDOW_SECS)
        free_bytes = free_pages * page_size
        by_table = {row.table: row for row in sized}
        dead_bytes = sum(
            round(row.bytes * min(count, row.rows) / row.rows)
            for table, count in dead_counts.items()
            if (row := by_table.get(table)) is not None and row.rows > 0 and count > 0
        )
        return MaintenanceReport(
            method=method,
            tables=tuple(sized),
            total_bytes=total_bytes,
            free_bytes=free_bytes,
            reclaimable_bytes=free_bytes + dead_bytes,
        )

    def trim(
        self,
        now: float | None = None,
        window_secs: float = DEFAULT_WINDOW_SECS,
        apply: bool = False,
    ) -> TrimResult:
        """Count derived rows, then delete them only when *apply* is true."""
        stamp = time.time() if now is None else now
        cutoff = event_cutoff(stamp, window_secs)
        targets = self._trim_targets(stamp, cutoff)
        with self._connect() as conn:
            counts = tuple(
                TableCount(target.table, self._count_target(conn, target)) for target in targets
            )
            if apply:
                for target in targets:
                    conn.execute(
                        f"DELETE FROM {_quoted(target.table)} WHERE {target.where}",
                        target.params,
                    )
        return TrimResult(tables=counts, applied=apply)

    def _freelist_pages(self, timeout: float = 1.0) -> int:
        """Free pages in the database, with a short wait for a competing writer."""
        conn = sqlite3.connect(str(self.path), timeout=timeout)
        try:
            return int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        finally:
            conn.close()

    def vacuum(self) -> VacuumResult:
        """Reclaim free pages outside a transaction; fail fast when the file is busy."""
        path = Path(self.path).expanduser()
        before_bytes = self._file_size()
        try:
            before_free = self._freelist_pages()
        except sqlite3.OperationalError as exc:
            raise MaintenanceBusy(
                "database is busy; stop other writers and retry `maint vacuum`"
            ) from exc
        try:
            conn = sqlite3.connect(str(path), timeout=1.0, isolation_level=None)
            try:
                conn.execute("PRAGMA busy_timeout = 1000")
                conn.execute("VACUUM")
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            text = str(exc).lower()
            if "locked" in text or "busy" in text:
                raise MaintenanceBusy(
                    "database is busy; stop other writers and retry `maint vacuum`"
                ) from exc
            raise
        return VacuumResult(
            before_bytes=before_bytes,
            after_bytes=self._file_size(),
            before_free_pages=before_free,
            after_free_pages=self._freelist_pages(),
            applied=True,
        )
