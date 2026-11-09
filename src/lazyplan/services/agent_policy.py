"""Which MCP writes an agent may perform directly.

The workbench starts the lazyplan MCP server in proposal mode. Operational
actions stay direct; structural changes are staged through `propose_*` tools and
reviewed by a human.
"""

from __future__ import annotations

DIRECT_WRITES: frozenset[str] = frozenset(
    {
        "claim_task",
        "claim_renew",
        "claim_release",
        "note_add",
        "block_task",
        "unblock_task",
        "comment_add",
        "comment_edit",
        "comment_resolve",
        "question_add",
        "question_resolve",
        "question_reopen",
        "touch_add",
        "touch_remove",
        "reference_link",
        "reference_unlink",
        "link_commit",
        "commit_refresh",
        "pull_request_link",
        "pull_request_unlink",
        "pull_request_refresh",
    }
)

STRUCTURAL_WRITES: frozenset[str] = frozenset(
    {
        "create_plan",
        "create_milestone",
        "create_task",
        "edit_row",
        "delete_row",
        "move_row",
        "criterion_add",
        "criterion_edit",
        "criterion_delete",
        "criterion_tick",
        "criterion_untick",
        "criterion_prove",
        "criterion_relate",
        "criterion_unrelate",
        "plan_approve",
        "finish_task",
    }
)

PROPOSAL_TOOLS: frozenset[str] = frozenset({"propose_plan", "propose_edit", "propose_task"})


def allowed_in_proposal_mode(tool: str) -> bool:
    """False for structural writes the human must apply from a proposal."""
    return tool not in STRUCTURAL_WRITES
