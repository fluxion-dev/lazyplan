"""Task context budgets: a fresh brief must leave room to do the work.

Token counts are estimates from characters, which is deterministic and close
enough for a hard ceiling. A task starts with a new session and a self-contained
brief; the brief must fit a small fraction of the model window so the rest is
available for reading, editing, and verification.
"""

from __future__ import annotations

from .agents import DEFAULT_CONTEXT

#: Starting brief budget as a percentage of the model context window.
DEFAULT_TASK_CONTEXT_PERCENT = 25
CHARS_PER_TOKEN = 4
#: Safe fallback when a caller cannot resolve a role's configured window.
DEFAULT_CONTEXT_WINDOW = min(DEFAULT_CONTEXT.values())


def estimate_tokens(text: str) -> int:
    """Estimate tokens from characters, rounding up."""
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def check_window(window: int) -> int:
    """Validate one positive context window."""
    if isinstance(window, bool) or not isinstance(window, int) or window < 1:
        raise ValueError("context window must be a positive integer")
    return window


def check_percent(percent: int) -> int:
    """Validate one whole-percentage budget between 1 and 100."""
    if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
        raise ValueError("context percent must be an integer between 1 and 100")
    return percent


def budget_tokens(window: int, percent: int = DEFAULT_TASK_CONTEXT_PERCENT) -> int:
    """The starting-brief budget in tokens."""
    check_window(window)
    check_percent(percent)
    return max(1, window * percent // 100)


def percent_used(tokens: int, window: int) -> float:
    """Percentage of a window one token count occupies, to one decimal."""
    check_window(window)
    return round(100.0 * max(0, tokens) / window, 1)
