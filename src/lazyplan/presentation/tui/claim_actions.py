"""Claim release and takeover actions."""

from __future__ import annotations

from ... import services
from ...core.errors import ClaimConflict
from .context import ContextMixin
from .screens import FilterPromptScreen


class ClaimMixin(ContextMixin):
    """Release a lease or take one over with a recorded reason."""

    def action_release_claim(self) -> None:
        self._release_claim(False)

    def action_force_release_claim(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify("a takeover needs a reason", timeout=3)
                return
            self._release_claim(True, reason.strip())

        self.push_screen(
            FilterPromptScreen(
                title=f"Take over T{task_id}? Why?",
                placeholder="reason for the takeover…",
                submit_label="Take over",
            ),
            reason_cb,
        )

    def _release_claim(self, force: bool, reason: str = "") -> None:
        task_id = self._selected_task()
        if task_id is None:
            return
        try:
            claim = services.release_claim(self.store, task_id, "tui", force=force)
        except ClaimConflict as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return
        if claim is None:
            self.notify(f"T{task_id} has no claim", timeout=3)
            return
        self._record_override(
            "claim force release" if force else "claim release", f"T{task_id}", reason
        )
        self.notify(f"released T{task_id} from {claim.actor}", timeout=3)
        self.refresh_all("claim released")
