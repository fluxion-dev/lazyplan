"""Status actions and the enforced-drift override prompt."""

from __future__ import annotations

from collections.abc import Callable

from ... import services
from ...core.entities import Status
from .context import ContextMixin


class StatusMixin(ContextMixin):
    """Cycle or move a row, warning before an enforced drift override."""

    def action_toggle_status(self) -> None:
        if self.selected is None:
            self.notify("select a row first (s advances status)")
            return
        kind, oid = self.selected
        left = self.store.open_criteria(kind, oid)
        current = self.store.get_parent(kind, oid)
        if left and (current is None or current.status != Status.DONE):
            self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
        if current is not None and current.status == Status.DOING:
            gate = self._drift_warning() or self._evidence_warning()
            if gate:
                self._prompt_drift_override(
                    gate, lambda reason: self._cycle_status(kind, oid, reason)
                )
                return
        self._cycle_status(kind, oid)

    def action_move(self, status: Status) -> None:
        """Move the selection to an explicit status (palette)."""
        if self.selected is None:
            self.notify("select a row first, then move it")
            return
        kind, oid = self.selected
        left = self.store.open_criteria(kind, oid)
        if status == Status.DONE and left:
            self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
        if status == Status.DONE:
            gate = self._drift_warning() or self._evidence_warning()
            if gate:
                self._prompt_drift_override(
                    gate, lambda reason: self._move_status(kind, oid, status, reason)
                )
                return
        self._move_status(kind, oid, status)

    def _prompt_drift_override(self, gate: str, apply: Callable[[str], None]) -> None:
        """Ask for a reason before overriding an enforced plan's drift."""
        self.prompt_reason(
            f"{gate}\nWhy override?",
            "reason for overriding the drift…",
            "Override",
            apply,
            "a drift override needs a reason",
        )

    def _cycle_status(self, kind: str, oid: int, reason: str = "") -> None:
        nxt = services.cycle_status(self.store, kind, oid, actor="tui", heal=self.heal)
        if nxt is None:
            self.notify("selected row no longer exists")
        else:
            self._record_gate_override(kind, oid, reason)
        self._saved(f"{kind} {oid} -> {nxt.value if nxt else '?'}")

    def _move_status(self, kind: str, oid: int, status: Status, reason: str = "") -> None:
        if not services.set_status(self.store, kind, oid, status, actor="tui", heal=self.heal):
            self.notify("selected row no longer exists")
            return
        self._record_gate_override(kind, oid, reason)
        self._saved(f"{kind} {oid} -> {status.value}")

    def _record_gate_override(self, kind: str, oid: int, reason: str) -> None:
        """Keep a prompted gate reason on the row after the move."""
        if reason.strip():
            self.store.add_note(kind, oid, f"Gate override by tui: {reason.strip()}", actor="tui")

    def _drift_warning(self) -> str | None:
        """Done-gate warning for the selected plan, when one applies."""
        plan_id = self._plan_ctx()
        if plan_id is None:
            return None
        return services.done_gate(self.store, plan_id)

    def _evidence_warning(self) -> str | None:
        """Finish-gate warning for the selected task, when one applies."""
        if self.selected is None or self.selected[0] != "task":
            return None
        return services.task_gate(self.store, self.selected[1])
