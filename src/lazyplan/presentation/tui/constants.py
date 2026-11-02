"""Small shared TUI constants."""

from __future__ import annotations

from ...core.entities import Status

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row
