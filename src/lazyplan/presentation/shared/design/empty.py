"""Shared empty states and standard user-facing messages."""

from __future__ import annotations

EMPTY_NO_PLANS = "No plans yet — press n to create one, or run: lpui plan add"
EMPTY_FEED = "No activity yet — agents write with `lpui task add`."
EMPTY_COMMITS = "(no commits linked)"


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
