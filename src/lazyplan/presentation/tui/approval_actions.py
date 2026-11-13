"""Plan approval and diff actions."""

from __future__ import annotations

from ... import services
from .context import ContextMixin
from .screens import FilterPromptScreen
from .screens.plan_diff import PlanDiffScreen


class ApprovalMixin(ContextMixin):
    """Record an approval revision or show the drift since the last one."""

    def action_approve_plan(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (approval is plan scope)")
            return
        latest = self.store.latest_revision(plan_id)
        enforced = latest.enforced if latest is not None else False

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            try:
                result = services.approve(
                    self.store,
                    plan_id,
                    actor="tui",
                    reason=reason.strip(),
                    enforced=enforced,
                )
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            state = "approved" if result.created else "already in sync"
            self.notify(f"P{plan_id} {state} at r{result.revision.revision}", timeout=4)
            self._saved("plan approved")

        self.push_screen(
            FilterPromptScreen(
                title=f"Approve P{plan_id}? Why? (required after drift)",
                placeholder="why this scope is approved…",
                submit_label="Approve",
            ),
            reason_cb,
        )

    def action_plan_diff(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (diff is plan scope)")
            return
        try:
            result = services.diff(self.store, plan_id)
        except (ValueError, KeyError) as exc:
            self.notify(str(exc), timeout=4)
            return
        self.push_screen(PlanDiffScreen(result))
