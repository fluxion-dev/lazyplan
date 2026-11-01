"""Note, comment, and mention rules shared by every surface."""

from __future__ import annotations


def validate_note(text: str) -> str:
    """Return the trimmed note body, rejecting an empty one."""
    body = text.strip()
    if not body:
        raise ValueError("note text must not be empty")
    return body


def validate_comment(text: str) -> str:
    """Return the trimmed comment body, rejecting an empty one."""
    body = text.strip()
    if not body:
        raise ValueError("comment text must not be empty")
    return body


def mention_needle(name: str | None) -> str:
    """Normalize a mention filter to the stored `@name` form."""
    return f"@{str(name or '').lstrip('@').lower()}"
