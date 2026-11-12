"""MCP maintenance tools: read-only report and snapshot-gated writes."""

from __future__ import annotations

from typing import Any, cast

from lazyplan import services

from ...core.ports.maintenance import MaintenancePort
from .base import McpBase
from .schema import id_schema as _id
from .schema import str_schema as _str
from .schema import tool as _tool


def _apply() -> dict:
    return {"type": "boolean"}


class MaintenanceToolsMixin(McpBase):
    """Report, archive, trim, vacuum, and restore over MCP."""

    def _maintenance_read_registry(self) -> dict[str, tuple[dict, Any]]:
        return {
            "maintenance_report": (
                _tool(
                    "maintenance_report",
                    "Database bytes and row counts per table, free pages, "
                    "and a reclaimable estimate.",
                    {},
                ),
                self._tool_maintenance_report,
            )
        }

    def _maintenance_write_registry(self) -> dict[str, tuple[dict, Any]]:
        """Write tools; apply=false previews, apply=true snapshots then writes."""
        return {
            "maintenance_archive": (
                _tool(
                    "maintenance_archive",
                    "Archive done plans and ended sessions past the window. "
                    "apply=false previews; apply=true writes after a verified snapshot.",
                    {"days": _str(), "apply": _apply()},
                    ["apply"],
                    False,
                ),
                self._tool_maintenance_archive,
            ),
            "maintenance_trim": (
                _tool(
                    "maintenance_trim",
                    "Delete derived rows only: expired claims, stale cache, closed PRs, "
                    "orphans, and old events. apply=false previews; apply=true snapshots first.",
                    {"days": _str(), "apply": _apply()},
                    ["apply"],
                    False,
                ),
                self._tool_maintenance_trim,
            ),
            "maintenance_vacuum": (
                _tool(
                    "maintenance_vacuum",
                    "Reclaim free pages. apply=false previews; apply=true snapshots first "
                    "and fails instead of waiting on a busy database.",
                    {"apply": _apply()},
                    ["apply"],
                    False,
                ),
                self._tool_maintenance_vacuum,
            ),
            "maintenance_restore": (
                _tool(
                    "maintenance_restore",
                    "Return one archived plan or session to the default views. "
                    "apply must be true; restore never runs as a preview.",
                    {"plan": _id(), "session": _id(), "apply": _apply()},
                    ["apply"],
                    False,
                ),
                self._tool_maintenance_restore,
            ),
        }

    def _maintenance_port(self) -> MaintenancePort:
        return cast(MaintenancePort, self._need_store())

    def _tool_maintenance_report(self, args: dict) -> object:
        del args
        return services.maintenance.report(self._maintenance_port()).to_dict()

    def _tool_maintenance_archive(self, args: dict) -> object:
        result = services.maintenance.archive(
            self._maintenance_port(),
            days=args.get("days") or None,
            apply=bool(args.get("apply")),
            actor=self.actor,
        )
        return result.to_dict()

    def _tool_maintenance_trim(self, args: dict) -> object:
        result = services.maintenance.trim(
            self._maintenance_port(),
            days=args.get("days") or None,
            apply=bool(args.get("apply")),
        )
        return result.to_dict()

    def _tool_maintenance_vacuum(self, args: dict) -> object:
        result = services.maintenance.vacuum(
            self._maintenance_port(), apply=bool(args.get("apply"))
        )
        return result.to_dict()

    def _tool_maintenance_restore(self, args: dict) -> object:
        if args.get("apply") is not True:
            raise ValueError("apply must be true to restore a row")
        plan_id = int(args["plan"]) if args.get("plan") is not None else None
        session_id = int(args["session"]) if args.get("session") is not None else None
        return services.maintenance.restore(
            self._maintenance_port(),
            plan_id=plan_id,
            session_id=session_id,
            actor=self.actor,
        ).to_dict()
