"""Note, comment, and mention rules shared by every surface."""

from __future__ import annotations


def cleaned_text(text: str, message: str) -> str:
    """Trimmed body, rejecting an empty one with the caller's message."""
    body = text.strip()
    if not body:
        raise ValueError(message)
    return body


def validate_note(text: str) -> str:
    """Return the trimmed note body, rejecting an empty one."""
    return cleaned_text(text, "note text must not be empty")


def validate_comment(text: str) -> str:
    """Return the trimmed comment body, rejecting an empty one."""
    return cleaned_text(text, "comment text must not be empty")


def mention_needle(name: str | None) -> str:
    """Normalize a mention filter to the stored `@name` form."""
    return f"@{str(name or '').lstrip('@').lower()}"
