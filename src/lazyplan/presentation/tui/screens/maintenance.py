"""Maintenance hub: report bytes, candidate counts, apply, and restore."""

from __future__ import annotations

from collections.abc import Callable

try:
    from textual.binding import Binding

    from ..navigation import NAV_BINDINGS
    from .forms import ConfirmScreen, FilterPromptScreen
    from .hub import HubEntry, HubScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from .... import services
from ....core.errors import MaintenanceBackupError, MaintenanceBusy
from ...shared import maintenance_presenter as view
from ...shared.design import escape_markup


def _error(exc: BaseException) -> str:
    return f"error: {escape_markup(str(exc))}"


if _TEXTUAL_OK:

    class MaintenanceScreen(HubScreen):
        """One maintenance surface: report, archive, trim, vacuum, and restore."""

        kind = "maintenance"
        title = "maintenance"
        empty = "No maintenance candidates."
        primary_hint = ("p", "preview")

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("p", "refresh", "Preview"),
            Binding("a", "apply_archive", "Archive"),
            Binding("t", "apply_trim", "Trim"),
            Binding("v", "apply_vacuum", "Vacuum"),
            Binding("R", "restore", "Restore"),
            Binding("r", "refresh", "Refresh"),
        ]

        def load_entries(self) -> list[HubEntry]:
            try:
                report = services.maintenance.report(self.store)
                archive = services.maintenance.archive(self.store, apply=False)
                trim = services.maintenance.trim(self.store, apply=False)
                vacuum = services.maintenance.vacuum(self.store, apply=False)
            except (MaintenanceBusy, MaintenanceBackupError) as exc:
                return [HubEntry(0, "maintenance unavailable", _error(exc), "error")]
            entries = [
                HubEntry(
                    0,
                    f"report  {report.total_bytes} bytes · {report.reclaimable_bytes} reclaimable",
                    view.report_text(report),
                    "report",
                ),
                HubEntry(
                    0,
                    f"archive  {len(archive.plans)} plan(s) · {len(archive.sessions)} session(s)",
                    view.archive_text(archive)
                    + "\n\nPress a to confirm and archive after a verified snapshot.",
                    "archive",
                ),
            ]
            for table, count in view.trim_counts(trim).items():
                entries.append(
                    HubEntry(
                        0,
                        f"trim  {table} · {count}",
                        f"target {table}\nrows   {count}\n\nTrim deletes derived rows only.",
                        "trim",
                        table,
                    )
                )
            entries.append(
                HubEntry(
                    0,
                    f"vacuum  {vacuum.before_bytes} bytes · {vacuum.before_free_pages} free page(s)",
                    view.vacuum_text(vacuum)
                    + "\n\nPress v to confirm and reclaim free pages after a verified snapshot.",
                    "vacuum",
                )
            )
            entries.append(
                HubEntry(
                    0,
                    "restore  archived plan or session",
                    "Press R and enter P3 or S4 to return an archived row to the default views.",
                    "restore",
                )
            )
            return entries

        def _after_write(self, note: str) -> None:
            self._reload()
            self.app.refresh_all(note)
            self.notify(note, timeout=4)

        def _confirm(
            self,
            text: str,
            label: str,
            action: Callable[[], str],
        ) -> None:
            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                try:
                    note = action()
                except (MaintenanceBusy, MaintenanceBackupError, ValueError, KeyError) as exc:
                    self.notify(_error(exc), timeout=5)
                    return
                self._after_write(note)

            self.app.push_screen(
                ConfirmScreen(text, confirm_label=label, variant="primary"),
                cb,
            )

        def action_apply_archive(self) -> None:
            preview = services.maintenance.archive(self.store, apply=False)
            if not preview.total:
                self.notify("nothing to archive", timeout=3)
                return

            def apply() -> str:
                result = services.maintenance.archive(self.store, apply=True)
                return f"archived {len(result.plans)} plan(s) and {len(result.sessions)} session(s)"

            self._confirm(
                f"Archive {len(preview.plans)} plan(s) and {len(preview.sessions)} session(s)?\n"
                "A verified snapshot is written first.",
                "Archive",
                apply,
            )

        def action_apply_trim(self) -> None:
            preview = services.maintenance.trim(self.store, apply=False)
            if not preview.total_rows:
                self.notify("nothing to trim", timeout=3)
                return

            def apply() -> str:
                result = services.maintenance.trim(self.store, apply=True)
                return f"trimmed {result.total_rows} derived row(s)"

            self._confirm(
                f"Trim {preview.total_rows} derived row(s)?\n"
                "User-authored plan text is never touched. A snapshot is written first.",
                "Trim",
                apply,
            )

        def action_apply_vacuum(self) -> None:
            preview = services.maintenance.vacuum(self.store, apply=False)
            if not preview.before_free_pages:
                self.notify("no free pages to reclaim", timeout=3)
                return

            def apply() -> str:
                result = services.maintenance.vacuum(self.store, apply=True)
                return f"freed {result.freed_bytes} bytes"

            self._confirm(
                f"Vacuum {preview.before_free_pages} free page(s)?\n"
                "VACUUM needs exclusive access and writes a snapshot first.",
                "Vacuum",
                apply,
            )

        def action_restore(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    kind, raw = text.strip()[:1].upper(), text.strip()[1:]
                    target = int(raw)
                    if kind == "P":
                        result = services.maintenance.restore(self.store, plan_id=target)
                    elif kind == "S":
                        result = services.maintenance.restore(self.store, session_id=target)
                    else:
                        raise ValueError("restore id must start with P or S")
                except (MaintenanceBusy, MaintenanceBackupError, ValueError, KeyError) as exc:
                    self.notify(_error(exc), timeout=5)
                    return
                self._after_write(f"restored {result.kind} #{result.id}")

            self.app.push_screen(
                FilterPromptScreen(
                    "Restore an archived row",
                    "plan or session id (P3 or S4)",
                    "Restore",
                ),
                cb,
            )
