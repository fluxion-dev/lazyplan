"""Status actions and the enforced-drift override prompt."""

from __future__ import annotations

from collections.abc import Callable

from ... import services
from ...core.entities import Status
from .context import ContextMixin
from .screens import FilterPromptScreen


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
            gate = self._drift_warning()
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
            gate = self._drift_warning()
            if gate:
                self._prompt_drift_override(
                    gate, lambda reason: self._move_status(kind, oid, status, reason)
                )
                return
        self._move_status(kind, oid, status)

    def _prompt_drift_override(self, gate: str, apply: Callable[[str], None]) -> None:
        """Ask for a reason before overriding an enforced plan's drift."""

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify("a drift override needs a reason", timeout=3)
                return
            apply(reason.strip())

        self.push_screen(
            FilterPromptScreen(
                title=f"{gate}\nWhy override?",
                placeholder="reason for overriding the drift…",
                submit_label="Override",
            ),
            reason_cb,
        )

    def _cycle_status(self, kind: str, oid: int, reason: str = "") -> None:
        nxt = services.cycle_status(self.store, kind, oid, actor="tui")
        if nxt is None:
            self.notify("selected row no longer exists")
        else:
            self._record_override("status", f"{kind} #{oid}", reason or nxt.value)
        self._saved(f"{kind} {oid} -> {nxt.value if nxt else '?'}")

    def _move_status(self, kind: str, oid: int, status: Status, reason: str = "") -> None:
        if not services.set_status(self.store, kind, oid, status, actor="tui"):
            self.notify("selected row no longer exists")
            return
        self._record_override("status", f"{kind} #{oid}", reason or status.value)
        self._saved(f"{kind} {oid} -> {status.value}")

    def _drift_warning(self) -> str | None:
        """Done-gate warning for the selected plan, when one applies."""
        plan_id = self._plan_ctx()
        if plan_id is None:
            return None
        return services.done_gate(self.store, plan_id)
