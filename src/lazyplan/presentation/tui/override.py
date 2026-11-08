"""Manual override mode: gate writes and show the banner."""

from __future__ import annotations

from collections.abc import Callable

from textual.widgets import Static

from ... import services
from .base import AppBase
from .screens import FilterPromptScreen
from .theme import next_theme

WRITE_ACTIONS = frozenset(
    {
        "add_criterion",
        "bulk_block",
        "bulk_done",
        "bulk_doing",
        "bulk_release",
        "criteria",
        "delete",
        "edit_selection",
        "force_release_claim",
        "git_capture",
        "new_context",
        "new_milestone",
        "new_plan",
        "new_task",
        "prove_criterion",
        "release_claim",
        "toggle_status",
        "undo_bulk",
    }
)

WRITE_COMMANDS = frozenset(
    {
        "new_plan",
        "new_milestone",
        "new_task",
        "add_criterion",
        "approve_plan",
        "prove_criterion",
        "add_question",
        "resolve_question",
        "reopen_question",
        "link_ref",
        "unlink_ref",
        "claim_task",
        "block_task",
        "unblock_task",
        "finish_task",
        "edit_selection",
        "move_todo",
        "move_doing",
        "move_done",
        "tick_criterion",
        "untick_criterion",
        "delete_selection",
        "git_capture",
        "bulk_doing",
        "bulk_done",
        "bulk_block",
        "bulk_release",
        "undo_bulk",
        "release_claim",
        "force_release_claim",
    }
)


class OverrideMixin(AppBase):
    """Read-only by default; one visible mode arms deliberate writes."""

    def _record_override(self, action: str, target: str, reason: str = "") -> None:
        """Write one audited override event for this manual change."""
        services.record_override(self.store, action, target, reason)

    def require_override(self, notify: bool = True) -> bool:
        """True when writes are armed; otherwise optionally explain why not."""
        if self.override_mode:
            return True
        if notify:
            self.notify("read-only — press O for manual override", timeout=3)
        return False

    def prompt_reason(
        self,
        title: str,
        placeholder: str,
        submit: str,
        callback: Callable[[str], None],
        empty_message: str = "a reason is required",
    ) -> None:
        """Ask for a non-empty reason and hand it to one callback."""

        def reason_cb(reason: str | None) -> None:
            if reason is None:
                return
            if not reason.strip():
                self.notify(empty_message, timeout=3)
                return
            callback(reason.strip())

        self.push_screen(
            FilterPromptScreen(title=title, placeholder=placeholder, submit_label=submit),
            reason_cb,
        )

    def _paint_mode(self) -> None:
        """Show or hide the manual-override banner."""
        banner = self.query_one("#mode", Static)
        banner.display = self.override_mode
        banner.update(
            "[reverse bold] MANUAL OVERRIDE [/] [dim]writes are deliberate and recorded[/]"
        )
        nav = self.query_one("#nav")
        nav.border_subtitle = "OVERRIDE" if self.override_mode else ""

    def action_toggle_override(self) -> None:
        """Toggle manual override mode; writes are blocked while off."""
        self.override_mode = not self.override_mode
        self.state.override_warned = False
        self._paint_mode()
        if self.override_mode:
            self.notify("manual override on — writes are deliberate", timeout=3)
        else:
            self.notify("read-only — writes are blocked", timeout=3)

    def action_cycle_theme(self) -> None:
        """Cycle mocha, void, and latte; the chart redraws after the CSS."""
        selected = next_theme(self.theme)
        self.theme = selected
        self.notify(f"theme: {selected.removeprefix('lazyplan-')}", timeout=2)
        self.call_after_refresh(self.metrics_controller.refresh)
