"""Evidence actions: record proof for a criterion."""

from __future__ import annotations

from ... import services
from .context import ContextMixin
from .screens.prove import prove_dialog


class EvidenceMixin(ContextMixin):
    """Open the prove form for the selected row's first open criterion."""

    def action_prove_criterion(self) -> None:
        if self.selected is None:
            self.notify("select a row first (p records evidence)")
            return
        kind, oid = self.selected

        def done(criterion_id: int, result: services.ProofResult) -> None:
            detail = result.evidence.command or result.evidence.note
            self._record_override("criterion prove", f"C{criterion_id}", detail)
            state = "proved" if result.ticked else "recorded, criterion stays open"
            self.notify(f"C{criterion_id} {state}", timeout=4)
            self._saved("evidence recorded")

        prove_dialog(self, self.store, kind, oid, done)
