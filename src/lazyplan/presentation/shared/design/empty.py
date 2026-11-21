"""Shared empty states and standard user-facing messages."""

from __future__ import annotations

EMPTY_NO_PLANS_TITLE = "No active plans"
EMPTY_NO_PLANS_HINT = "press n to create one"
EMPTY_NO_PLANS = f"{EMPTY_NO_PLANS_TITLE} — {EMPTY_NO_PLANS_HINT}"
PANEL_PLAN_QUEUE_TITLE = "plan queue"
PANEL_PLAN_DRAFTS_TITLE = "plan drafts"
PANEL_PLAN_REVIEW_TITLE = "plan review"
EMPTY_PLAN_QUEUE_TITLE = "No plans in the plan queue"
EMPTY_PLAN_QUEUE_HINT = "promote a reviewed draft to queue it"
EMPTY_PLAN_DRAFTS_TITLE = "No plan drafts"
EMPTY_PLAN_DRAFTS_HINT = "press n to draft a plan"
EMPTY_PLAN_REVIEW_TITLE = "No finished plans"
EMPTY_PLAN_REVIEW_HINT = "done plans show here"
EMPTY_FEED = "No activity yet — agents write with `lpui task add`."
EMPTY_COMMITS = "(no commits linked)"
EMPTY_NEEDS = "nothing needs you"
EMPTY_APPROVAL = "no approved revision"


def empty_state(title: str, hint: str) -> str:
    """Bold capitalized title and one dim line showing how to leave it."""
    head = str(title).strip()
    if head:
        head = head[0].upper() + head[1:]
    return f"[bold]{head}[/]\n[dim]{str(hint).strip()}[/]"


def msg_not_found(kind: str, obj_id: int) -> str:
    """Standard '<kind> #<id> not found' message."""
    return f"{kind} {obj_id} not found"


def msg_no_vcs() -> str:
    """Standard VCS-unavailable message (linking disabled outside a git repo)."""
    return "error: no VCS backend available (not in a git repo)"


def msg_no_head() -> str:
    """Standard no-commit message (git repo with no HEAD yet)."""
    return "error: no HEAD commit found (empty git repo?)"


def msg_error(exc: BaseException) -> str:
    """Standard 'error: <exc>' message."""
    return f"error: {exc}"
