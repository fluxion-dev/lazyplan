"""The maintenance port: report, archive, restore, trim, vacuum, and backup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from ..policies.maintenance import DEFAULT_WINDOW_SECS
from .planning import PlanningPort
from .sessions import SessionsReadPort


@dataclass(frozen=True)
class TableBytes:
    """Bytes and rows owned by one table."""

    table: str
    bytes: int = 0
    rows: int = 0

    def to_dict(self) -> dict:
        """JSON-safe row for reports."""
        return {"table": self.table, "bytes": self.bytes, "rows": self.rows}


@dataclass(frozen=True)
class TableCount:
    """Rows removed from, or present in, one table."""

    table: str
    rows: int = 0

    def to_dict(self) -> dict:
        """JSON-safe row for trim results."""
        return {"table": self.table, "rows": self.rows}


@dataclass(frozen=True)
class MaintenanceReport:
    """Database size and row counts, with the measurement method named."""

    method: str = "dbstat"
    tables: tuple[TableBytes, ...] = ()
    used_bytes: int = 0
    file_bytes: int = 0
    free_bytes: int = 0
    reclaimable_bytes: int = 0
    window_days: float = 7.0

    def to_dict(self) -> dict:
        """JSON-safe report for scripts and agents."""
        return {
            "method": self.method,
            "tables": [row.to_dict() for row in self.tables],
            "used_bytes": self.used_bytes,
            "file_bytes": self.file_bytes,
            "free_bytes": self.free_bytes,
            "reclaimable_bytes": self.reclaimable_bytes,
            "window_days": self.window_days,
        }


@dataclass(frozen=True)
class ArchiveResult:
    """Archive or restore preview: the rows in scope and whether it wrote."""

    plans: tuple[int, ...] = ()
    sessions: tuple[int, ...] = ()
    applied: bool = False

    @property
    def total(self) -> int:
        """Rows in scope across both kinds."""
        return len(self.plans) + len(self.sessions)

    def to_dict(self) -> dict:
        """JSON-safe result for previews and writes."""
        return {
            "plans": list(self.plans),
            "sessions": list(self.sessions),
            "applied": self.applied,
            "total": self.total,
        }


@dataclass(frozen=True)
class TrimResult:
    """Rows trimmed per table, with the total and whether it wrote."""

    tables: tuple[TableCount, ...] = ()
    applied: bool = False

    @property
    def total_rows(self) -> int:
        """Rows trimmed across every table."""
        return sum(row.rows for row in self.tables)

    def to_dict(self) -> dict:
        """JSON-safe trim result."""
        return {
            "tables": [row.to_dict() for row in self.tables],
            "total_rows": self.total_rows,
            "applied": self.applied,
        }


@dataclass(frozen=True)
class VacuumResult:
    """File size and free pages before and after VACUUM."""

    before_bytes: int = 0
    after_bytes: int = 0
    before_free_pages: int = 0
    after_free_pages: int = 0
    applied: bool = True

    @property
    def freed_bytes(self) -> int:
        """Bytes the file shrank by; never negative."""
        return max(self.before_bytes - self.after_bytes, 0)

    def to_dict(self) -> dict:
        """JSON-safe vacuum result."""
        return {
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "before_free_pages": self.before_free_pages,
            "after_free_pages": self.after_free_pages,
            "freed_bytes": self.freed_bytes,
            "applied": self.applied,
        }


@dataclass(frozen=True)
class BackupResult:
    """One integrity-checked snapshot written before a mutation."""

    path: str = ""
    bytes: int = 0
    verified: bool = False
    details: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """JSON-safe backup result."""
        return {
            "path": self.path,
            "bytes": self.bytes,
            "verified": self.verified,
            "details": list(self.details),
        }


@dataclass(frozen=True)
class RestoreResult:
    """One archived plan or session returned to the default views."""

    kind: str = ""
    id: int = 0
    restored: bool = False

    def to_dict(self) -> dict:
        """JSON-safe restore result."""
        return {"kind": self.kind, "id": self.id, "restored": self.restored}


class MaintenancePort(PlanningPort, SessionsReadPort, Protocol):
    """Persistence surface the maintenance use cases need."""

    def archive_plan(
        self, plan_id: int, actor: str = "human", now: float | None = None
    ) -> bool: ...

    def restore_plan(
        self, plan_id: int, actor: str = "human", now: float | None = None
    ) -> bool: ...

    def archive_sessions(
        self,
        session_ids: Sequence[int],
        actor: str = "human",
        now: float | None = None,
    ) -> int: ...

    def restore_session(
        self, session_id: int, actor: str = "human", now: float | None = None
    ) -> bool: ...

    def report(self, window_secs: float = DEFAULT_WINDOW_SECS) -> MaintenanceReport: ...

    def trim(
        self,
        now: float | None = None,
        window_secs: float = DEFAULT_WINDOW_SECS,
        apply: bool = False,
    ) -> TrimResult: ...

    def vacuum(self) -> VacuumResult: ...

    def vacuum_preview(self) -> VacuumResult: ...

    def backup(self, label: str = "") -> BackupResult: ...
