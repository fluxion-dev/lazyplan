"""Maintenance persistence: database size, per-table bytes, row counts, and trim."""

from __future__ import annotations

import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..core.errors import MaintenanceBackupError, MaintenanceBusy
from ..core.policies.maintenance import DEFAULT_WINDOW_SECS, event_cutoff
from ..core.ports.maintenance import (
    BackupResult,
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


@dataclass(frozen=True)
class _ReportMeasure:
    """Raw page and row facts behind one maintenance report."""

    page_size: int
    free_pages: int
    method: str
    tables: tuple[TableBytes, ...]
    used_bytes: int
    trim_counts: dict[str, int]


def _quoted(name: str) -> str:
    """Quote one SQLite identifier."""
    return '"' + name.replace('"', '""') + '"'


def _table_rows(conn: sqlite3.Connection, table: str) -> int:
    """Exact row count for one table."""
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {_quoted(table)}").fetchone()
    return int(row["count"] if row is not None else 0)


def _missing_owner(kind_column: str, id_column: str = "parent_id") -> str:
    """Predicate matching rows whose plan, milestone, or task parent is gone."""
    return (
        f"({kind_column}='plan' AND NOT EXISTS (SELECT 1 FROM plans WHERE id={id_column}))"
        f" OR ({kind_column}='milestone'"
        f" AND NOT EXISTS (SELECT 1 FROM milestones WHERE id={id_column}))"
        f" OR ({kind_column}='task'"
        f" AND NOT EXISTS (SELECT 1 FROM tasks WHERE id={id_column}))"
    )


_MISSING_PARENT = _missing_owner("parent_kind")
_MISSING_KIND = _missing_owner("kind", "row_id")
_MISSING_ROW_KIND = _missing_owner("row_kind", "row_id")


class MaintenanceMixin(StoreBase):
    """Maintenance reads and writes shared by the CLI, TUI, and MCP."""

    def _file_size(self) -> int:
        """Database size in bytes, including WAL and shared-memory sidecars."""
        path = Path(self.path).expanduser()
        total = 0
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
            try:
                total += candidate.stat().st_size
            except OSError:
                continue
        return total

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
    ) -> tuple[list[str], dict[str, list[str]]]:
        """User tables and the indexes owned by each."""
        rows = conn.execute("SELECT type, name, tbl_name FROM sqlite_master").fetchall()
        tables = [str(row["name"]) for row in rows if row["type"] == "table"]
        indexes: dict[str, list[str]] = {}
        for row in rows:
            if row["type"] == "index":
                indexes.setdefault(str(row["tbl_name"]), []).append(str(row["name"]))
        return tables, indexes

    def _table_sizes(
        self,
        conn: sqlite3.Connection,
        tables: list[str],
        indexes: dict[str, list[str]],
        page_bytes: dict[str, int],
    ) -> tuple[TableBytes, ...]:
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
        return tuple(rows)

    @staticmethod
    def _claim_targets(now: float) -> tuple[TrimTarget, ...]:
        """Expired leases and the touch-points they carried."""
        return (
            TrimTarget(
                "task_touchpoints",
                "task_id IN (SELECT task_id FROM task_claims WHERE expires_at <= ?)",
                (now,),
            ),
            TrimTarget("task_claims", "expires_at <= ?", (now,)),
        )

    @staticmethod
    def _forge_targets(cutoff: float) -> tuple[TrimTarget, ...]:
        """Stale cache entries and pull requests that are already closed."""
        return (
            TrimTarget("forge_cache", "fetched_at < ?", (cutoff,)),
            TrimTarget(
                "forge_links",
                "lower(state) IN ('closed', 'merged') OR merged_at <> ''",
            ),
        )

    @staticmethod
    def _orphan_targets() -> tuple[TrimTarget, ...]:
        """Derived link rows whose plan, milestone, task, or criterion is gone.

        User-authored text (criteria, evidence, notes, comments) is never a
        trim target, even when its parent row is missing.
        """
        return (
            TrimTarget(
                "criterion_links",
                "NOT EXISTS (SELECT 1 FROM criteria c WHERE c.id=criterion_id)"
                " OR NOT EXISTS (SELECT 1 FROM tasks t WHERE t.id=task_id)",
            ),
            TrimTarget("entity_keys", _MISSING_KIND),
            TrimTarget("entity_repos", _MISSING_PARENT),
            TrimTarget("issue_links", _MISSING_ROW_KIND),
            TrimTarget("vcs_links", _MISSING_PARENT),
        )

    @staticmethod
    def _event_targets(cutoff: float) -> tuple[TrimTarget, ...]:
        """Old non-status events plus older status events.

        The newest plan status event per plan is the finished/archive policy
        input and always survives; task and milestone status events do not.
        """
        where = (
            "ts < ? AND (action <> 'status' OR kind <> 'plan'"
            " OR detail NOT LIKE 'plan #% -> %'"
            " OR id NOT IN ("
            "SELECT MAX(id) FROM events"
            " WHERE kind='plan' AND action='status' AND detail LIKE 'plan #% -> %'"
            " GROUP BY substr(detail, 7, instr(substr(detail, 7), ' ') - 1)))"
        )
        return (TrimTarget("events", where, (cutoff,)),)

    @classmethod
    def _trim_targets(cls, now: float, cutoff: float) -> tuple[TrimTarget, ...]:
        """Every derived-row delete trim may make, in a safe order."""
        return (
            *cls._claim_targets(now),
            *cls._forge_targets(cutoff),
            *cls._orphan_targets(),
            *cls._event_targets(cutoff),
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

    def _measure(self, conn: sqlite3.Connection, now: float, window_secs: float) -> _ReportMeasure:
        """Collect page sizes, per-table bytes, and trim candidates."""
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        free_pages = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        tables, indexes = self._schema_objects(conn)
        try:
            page_bytes = self._dbstat_bytes(conn)
            method = "dbstat"
        except sqlite3.OperationalError:
            page_bytes = {}
            method = "page_count"
        if method == "dbstat":
            sized = self._table_sizes(conn, tables, indexes, page_bytes)
            used_bytes = sum(row.bytes for row in sized)
        else:
            sized = tuple(TableBytes(table, 0, _table_rows(conn, table)) for table in tables)
            used_bytes = page_count * page_size
        return _ReportMeasure(
            page_size=page_size,
            free_pages=free_pages,
            method=method,
            tables=sized,
            used_bytes=used_bytes,
            trim_counts=self._trim_counts(conn, now, window_secs),
        )

    @staticmethod
    def _reclaimable_bytes(measure: _ReportMeasure) -> int:
        """Free pages plus the share of each table held by trim candidates."""
        by_table = {row.table: row for row in measure.tables}
        dead_bytes = sum(
            round(row.bytes * min(count, row.rows) / row.rows)
            for table, count in measure.trim_counts.items()
            if (row := by_table.get(table)) is not None and row.rows > 0 and count > 0
        )
        return measure.free_pages * measure.page_size + dead_bytes

    def report(self, window_secs: float = DEFAULT_WINDOW_SECS) -> MaintenanceReport:
        """Per-table bytes and row counts, plus free and reclaimable pages."""
        now = time.time()
        with self._connect() as conn:
            measure = self._measure(conn, now, window_secs)
        return MaintenanceReport(
            method=measure.method,
            tables=measure.tables,
            used_bytes=measure.used_bytes,
            file_bytes=self._file_size(),
            free_bytes=measure.free_pages * measure.page_size,
            reclaimable_bytes=self._reclaimable_bytes(measure),
            window_days=round(window_secs / 86400, 3),
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
                self._delete_targets(conn, targets)
        return TrimResult(tables=counts, applied=apply)

    @staticmethod
    def _delete_targets(conn: sqlite3.Connection, targets: tuple[TrimTarget, ...]) -> None:
        """Run one target builder's deletes inside the caller's transaction."""
        for target in targets:
            conn.execute(
                f"DELETE FROM {_quoted(target.table)} WHERE {target.where}",
                target.params,
            )

    def _freelist_pages(self, timeout: float = 1.0) -> int:
        """Free pages in the database, with a short wait for a competing writer."""
        conn = sqlite3.connect(str(self.path), timeout=timeout)
        try:
            return int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        finally:
            conn.close()

    @staticmethod
    def _busy_error() -> MaintenanceBusy:
        """One clear message for a blocked vacuum."""
        return MaintenanceBusy("database is busy; stop other writers and retry `maint vacuum`")

    def _current_free_pages(self) -> int:
        """Free pages, translated to a clear busy error."""
        try:
            return self._freelist_pages()
        except sqlite3.OperationalError as exc:
            raise self._busy_error() from exc

    def _run_vacuum(self, path: Path) -> None:
        """VACUUM on a dedicated autocommit connection with a short timeout."""
        try:
            conn = sqlite3.connect(str(path), timeout=1.0, isolation_level=None)
        except sqlite3.OperationalError as exc:
            raise self._busy_error() from exc
        try:
            conn.execute("PRAGMA busy_timeout = 1000")
            journal = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            conn.execute("VACUUM")
            if journal == "wal":
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError as exc:
            text = str(exc).lower()
            if "locked" in text or "busy" in text:
                raise self._busy_error() from exc
            raise
        finally:
            conn.close()

    def vacuum(self) -> VacuumResult:
        """Reclaim free pages outside a transaction; fail fast when the file is busy."""
        path = Path(self.path).expanduser()
        before_bytes = self._file_size()
        before_free = self._current_free_pages()
        self._run_vacuum(path)
        return VacuumResult(
            before_bytes=before_bytes,
            after_bytes=self._file_size(),
            before_free_pages=before_free,
            after_free_pages=self._current_free_pages(),
            applied=True,
        )

    def vacuum_preview(self) -> VacuumResult:
        """Current file size and free pages, without reclaiming anything."""
        free_pages = self._current_free_pages()
        size = self._file_size()
        return VacuumResult(
            before_bytes=size,
            after_bytes=size,
            before_free_pages=free_pages,
            after_free_pages=free_pages,
            applied=False,
        )

    @staticmethod
    def _integrity_ok(conn: sqlite3.Connection) -> bool:
        """True when SQLite's own integrity check returns only ok rows."""
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        return bool(rows) and all(str(row[0]).lower() == "ok" for row in rows)

    @staticmethod
    def _backup_counts(conn: sqlite3.Connection) -> dict[str, int]:
        """Counts compared between the live database and its snapshot."""
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("plans", "tasks", "events")
        }

    @staticmethod
    def _remove_snapshot(target: Path, bindings: Path) -> None:
        """Delete a failed snapshot and its binding copy."""
        try:
            target.unlink()
        except OSError:
            pass
        shutil.rmtree(bindings, ignore_errors=True)

    @staticmethod
    def _snapshot_paths(source_path: Path) -> tuple[Path, Path]:
        """Timestamped database snapshot and its binding-directory peer."""
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        target = source_path.with_name(f"{source_path.name}.bak-{stamp}")
        return target, target.with_name(f"{target.name}.bindings")

    def _snapshot_database(self, source_path: Path, target: Path) -> dict[str, int]:
        """Copy with the backup API, close, then verify the snapshot read-only."""
        bindings = target.with_name(f"{target.name}.bindings")
        live_counts: dict[str, int] = {}
        error: Exception | None = None
        source: sqlite3.Connection | None = None
        snapshot: sqlite3.Connection | None = None
        try:
            source = sqlite3.connect(str(source_path), timeout=5.0)
            snapshot = sqlite3.connect(str(target), timeout=5.0)
            source.backup(snapshot)
            live_counts = self._backup_counts(source)
        except (sqlite3.Error, OSError) as exc:
            error = exc
        finally:
            if snapshot is not None:
                snapshot.close()
            if source is not None:
                source.close()
        if error is not None:
            self._remove_snapshot(target, bindings)
            raise MaintenanceBackupError(f"snapshot failed: {error}") from error
        verifier = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=5.0)
        try:
            integrity = self._integrity_ok(verifier)
            snapshot_counts = self._backup_counts(verifier)
        except sqlite3.Error as exc:
            verifier.close()
            self._remove_snapshot(target, bindings)
            raise MaintenanceBackupError(f"snapshot verification failed: {exc}") from exc
        verifier.close()
        if not integrity or live_counts != snapshot_counts:
            self._remove_snapshot(target, bindings)
            raise MaintenanceBackupError("snapshot failed integrity or count verification")
        return snapshot_counts

    def _snapshot_bindings(self, source_path: Path, target: Path) -> Path | None:
        """Copy the session binding directory beside the database snapshot."""
        source_bindings = source_path.parent / "sessions" / "bindings"
        if not source_bindings.is_dir():
            return None
        bindings = target.with_name(f"{target.name}.bindings")
        try:
            shutil.copytree(source_bindings, bindings)
        except OSError as exc:
            self._remove_snapshot(target, bindings)
            raise MaintenanceBackupError(f"binding snapshot failed: {exc}") from exc
        return bindings

    def backup(self, label: str = "") -> BackupResult:
        """Copy the database beside itself, verify it, and snapshot bindings."""
        source_path = Path(self.path).expanduser()
        target, _bindings = self._snapshot_paths(source_path)
        counts = self._snapshot_database(source_path, target)
        details = [
            f"plans={counts['plans']}",
            f"tasks={counts['tasks']}",
            f"events={counts['events']}",
        ]
        if label:
            details.append(f"label={label}")
        bindings = self._snapshot_bindings(source_path, target)
        if bindings is not None:
            details.append(f"bindings={bindings}")
        return BackupResult(
            path=str(target),
            bytes=target.stat().st_size,
            verified=True,
            details=tuple(details),
        )
