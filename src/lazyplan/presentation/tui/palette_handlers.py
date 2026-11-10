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
        "add_question": app.action_add_question,
        "resolve_question": app.action_resolve_question,
        "reopen_question": app.action_reopen_question,
        "link_ref": app.action_link_ref,
        "unlink_ref": app.action_unlink_ref,
        "claim_task": app.action_claim_task,
        "block_task": app.action_block_task,
        "unblock_task": app.action_unblock_task,
        "finish_task": app.action_finish_task,
        "plan_diff": app.action_plan_diff,
        "edit_selection": app.action_edit_selection,
        "move_todo": lambda: app.action_move(Status.TODO),
        "move_doing": lambda: app.action_move(Status.DOING),
        "move_done": lambda: app.action_move(Status.DONE),
        "delete_selection": app.action_delete,
        "fold": app.action_fold,
        "fold_all": app.action_fold_all,
        "filter_text": app.action_filter_text,
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
        "open_criteria_hub": app.action_open_criteria_hub,
        "open_evidence_hub": app.action_open_evidence_hub,
        "open_questions_hub": app.action_open_questions_hub,
        "open_references_hub": app.action_open_references_hub,
        "open_claims_hub": app.action_open_claims_hub,
        "open_sessions_hub": app.action_open_sessions_hub,
        "open_comments_hub": app.action_open_comments_hub,
        "open_pull_requests_hub": app.action_open_pull_requests_hub,
        "open_activity_hub": app.action_open_activity_hub,
        "refresh_prs": app.action_refresh_prs,
        "link_pr": app.action_link_pr,
        "unlink_pr": app.action_unlink_pr,
        "command_palette": app.action_command_palette,
        "cycle_theme": app.action_cycle_theme,
        "toggle_timeline": app.action_toggle_timeline,
        "export_md": app.action_export_md,
        "help": app.action_help,
        "update_prompt": app.action_update_prompt,
        "quit": app.exit,
    }
