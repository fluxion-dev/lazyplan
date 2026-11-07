"""Palette command handlers for the app mixins."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...core.entities import Status


def palette_handlers(app: Any) -> dict[str, Callable[[], None]]:
    """Map the shared registry handler names to the app's action methods."""
    return {
        "new_plan": app.action_new_plan,
        "new_milestone": app.action_new_milestone,
        "new_task": app.action_new_task,
        "add_criterion": app.action_add_criterion,
        "approve_plan": app.action_approve_plan,
        "prove_criterion": app.action_prove_criterion,
        "plan_diff": app.action_plan_diff,
        "edit_selection": app.action_edit_selection,
        "move_todo": lambda: app.action_move(Status.TODO),
        "move_doing": lambda: app.action_move(Status.DOING),
        "move_done": lambda: app.action_move(Status.DONE),
        "tick_criterion": app.action_criteria,
        "untick_criterion": app.action_untick_criterion,
        "delete_selection": app.action_delete,
        "open_detail": app.action_open_detail,
        "fold": app.action_fold,
        "fold_all": app.action_fold_all,
        "filter_text": app.action_filter_text,
        "filter_status": app.action_filter_status,
        "filter_source": app.action_filter_source,
        "toggle_show_all": app.action_toggle_show_all,
        "refresh": app.action_refresh,
        "git_status": app.action_git_status,
        "git_refresh": app.action_git_refresh,
        "git_capture": app.action_git_capture,
        "toggle_mark": app.action_toggle_mark,
        "clear_marks": app.action_clear_marks,
        "bulk_doing": app.action_bulk_doing,
        "bulk_done": app.action_bulk_done,
        "bulk_block": app.action_bulk_block,
        "bulk_release": app.action_bulk_release,
        "undo_bulk": app.action_undo_bulk,
        "release_claim": app.action_release_claim,
        "force_release_claim": app.action_force_release_claim,
        "open_pr": app.action_open_pr,
        "source_trail": app.action_source_trail,
        "command_palette": app.action_command_palette,
        "cycle_theme": app.action_cycle_theme,
        "toggle_override": app.action_toggle_override,
        "export_md": app.action_export_md,
        "help": app.action_help,
        "update_prompt": app.action_update_prompt,
        "quit": app.exit,
    }
