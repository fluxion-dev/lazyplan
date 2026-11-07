"""Claim release and takeover actions."""

from __future__ import annotations

from ... import services
from ...core.errors import ClaimConflict
from ...services.coordination import overlaps
from .context import ContextMixin
from .screens import FilterPromptScreen


class ClaimMixin(ContextMixin):
    """Claim work, release a lease, block, or unblock with reasons."""

    def action_claim_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return
        found = overlaps(self.store, task_id)
        if found:
            summary = "; ".join(
                f"T{int(item['task_id'])} @{item['actor']} ({', '.join(item['patterns'])})"
                for item in found[:3]
            )

            def reason_cb(reason: str | None) -> None:
                if reason is None:
                    return
                if not reason.strip():
                    self.notify("an overlap override needs a reason", timeout=3)
                    return
                self._claim(task_id, reason.strip(), force=True)

            self.push_screen(
                FilterPromptScreen(
                    title=f"Claim T{task_id}? Overlaps {summary}. Why?",
                    placeholder="reason for the overlap override…",
                    submit_label="Claim",
                ),
                reason_cb,
            )
            return
        self._claim(task_id)

    def _claim(self, task_id: int, reason: str = "", force: bool = False) -> None:
        try:
            services.start_claim(self.store, task_id, "tui", force=force)
        except Exception as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return
        self._record_override("claim", f"T{task_id}", reason)
        self.notify(f"claimed T{task_id}", timeout=3)
        self._saved("task claimed")

    def action_block_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify("a block needs a reason", timeout=3)
                return
            try:
                services.block_task(self.store, task_id, reason.strip(), actor="tui")
            except (ValueError, KeyError) as exc:
                self.notify(str(exc), severity="error", timeout=5)
                return
            self._record_override("block", f"T{task_id}", reason.strip())
            self.notify(f"blocked T{task_id}", timeout=3)
            self._saved("task blocked")

        self.push_screen(
            FilterPromptScreen(
                title=f"Block T{task_id}? Why?",
                placeholder="what is it waiting on?",
                submit_label="Block",
            ),
            reason_cb,
        )

    def action_unblock_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return
        try:
            services.unblock_task(self.store, task_id, actor="tui")
        except KeyError as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return
        self._record_override("unblock", f"T{task_id}")
        self.notify(f"unblocked T{task_id}", timeout=3)
        self._saved("task unblocked")

    def action_release_claim(self) -> None:
        self._release_claim(False)

    def action_force_release_claim(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return
        found = overlaps(self.store, task_id)
        summary = ""
        if found:
            summary = " Overlaps " + "; ".join(
                f"T{int(item['task_id'])} ({', '.join(item['patterns'])})" for item in found[:3]
            )

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify("a takeover needs a reason", timeout=3)
                return
            self._release_claim(True, reason.strip())

        self.push_screen(
            FilterPromptScreen(
                title=f"Take over T{task_id}?{summary} Why?",
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
