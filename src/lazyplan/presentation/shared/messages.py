"""Custom TUI messages: selection changes and row actions.

Events are also messages (guide/events). Widgets post these; they bubble
child -> parent -> App. App handles them via @on, keeping data flow
messages-up, attributes-down.
"""

from __future__ import annotations

try:
    from textual.message import Message

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

    class Message:  # type: ignore[no-redef]
        """Fallback when Textual is missing (headless/CI)."""

        bubble = True


if _TEXTUAL_OK:

    class SelectionChanged(Message):
        """Posted when the tree cursor selects a new plan/milestone/task."""

        bubble = True

        def __init__(self, kind: str, oid: int) -> None:
            super().__init__()
            self.kind = kind
            self.oid = oid

    class RowAction(Message):
        """Generic row intent: toggle-status, open-detail, fold-all, etc."""

        bubble = True

        def __init__(self, action: str, kind: str | None, oid: int | None) -> None:
            super().__init__()
            self.action = action
            self.kind = kind
            self.oid = oid
