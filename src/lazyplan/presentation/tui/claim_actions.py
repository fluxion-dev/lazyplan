"""Claim release and takeover actions."""

from __future__ import annotations

from ... import services
from ...core.errors import ClaimConflict
from ...services.coordination import overlaps
from .context import ContextMixin


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
            self.prompt_reason(
                f"Claim T{task_id}? Overlaps {summary}. Why?",
                "reason for the overlap override…",
                "Claim",
                lambda reason: self._claim(task_id, reason, force=True),
                "an overlap override needs a reason",
            )
            return
        self._claim(task_id)

    def _claim(self, task_id: int, reason: str = "", force: bool = False) -> None:
        try:
            services.start_claim(self.store, task_id, "tui", note=reason, force=force)
        except Exception as exc:
            self.notify(str(exc), severity="error", timeout=5)
            return
        self.notify(f"claimed T{task_id}", timeout=3)
        self._saved("task claimed")

    def action_block_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return

        def block(reason: str) -> None:
            try:
                services.block_task(self.store, task_id, reason, actor="tui")
            except (ValueError, KeyError) as exc:
                self.notify(str(exc), severity="error", timeout=5)
                return
            self.notify(f"blocked T{task_id}", timeout=3)
            self._saved("task blocked")

        self.prompt_reason(
            f"Block T{task_id}? Why?",
            "what is it waiting on?",
            "Block",
            block,
            "a block needs a reason",
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
        self.prompt_reason(
            f"Take over T{task_id}?{summary} Why?",
            "reason for the takeover…",
            "Take over",
            lambda reason: self._release_claim(True, reason),
            "a takeover needs a reason",
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
        if force and reason.strip():
            self.store.add_note(
                "task", task_id, f"Force release by tui: {reason.strip()}", actor="tui"
            )
        self.notify(f"released T{task_id} from {claim.actor}", timeout=3)
        self.refresh_all("claim released")
