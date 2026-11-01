"""Textual app: filters."""

from __future__ import annotations

try:
    from textual import events, on  # noqa: F401
    from textual.app import App, ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.reactive import reactive  # noqa: F401
    from textual.widgets import Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ..tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from .. import stats as stats_mod
from ..design import (
    truncate,
)
from ..models import Status
from ..repo import repo_label
from .base import AppBase
from .screens import (
    FilterPromptScreen,
)

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row


if _TEXTUAL_OK:

    class FilterMixin(AppBase):
        SOURCE_FILTERS = (
            "all",
            "linked",
            "pr",
            "stale",
            "unlinked",
            "claims",
            "blocked",
            "attention",
        )
        """Filters behavior."""

        def _open_filter_prompt(self) -> None:
            """Prompt for tree filter text; empty clears the filter."""

            def cb(text: str | None) -> None:
                if text is None:
                    return
                self.filter_text = text
                self._pending_note = f"filter: {text}" if text else "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all(self._pending_note)

            self.push_screen(FilterPromptScreen(), cb)

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        def action_toggle_show_all(self) -> None:
            self.show_all = not self.show_all
            self.refresh_all("showing all plans" if self.show_all else "showing recent plans")

        def _refresh_status(self, note: str = "") -> None:
            """Update only the statusbar, without rebuilding the tree."""
            try:
                self.query_one("#status", Label).update(
                    self._status_text(self.store.counts(), note)
                )
            except Exception:
                pass

        def _status_text(self, counts: dict[str, int], note: str) -> str:
            """Human counts, filter state, update notice, and the latest event."""
            open_tasks = counts["tasks"] - counts["tasks_done"]
            bits = [
                repo_label(self.store.path),
                f"{counts['plans']} plans",
                f"{open_tasks} open",
                f"{counts['plans_doing']} doing",
            ]
            attention = len(stats_mod.attention_ids(self.store))
            if attention:
                bits.append(f"attention {attention}")
            if self.marked:
                bits.append(f"marked {len(self.marked)}")
            if self.status_filter is not None:
                bits.append(f"status {self.status_filter.value}")
            if self.source_filter != "all":
                bits.append(f"source {self.source_filter}")
            if self.filter_text.strip():
                bits.append(f'filter "{self.filter_text.strip()}"')
            if not self.show_all:
                bits.append(f"recent {services.DEFAULT_PLAN_LIMIT}")
            if self._update_notice is not None:
                bits.append(
                    f"update v{self._update_latest}" if self._update_latest else "update available"
                )
            text = " · ".join(bits)
            if note:
                text += f" — {note}"
            events = self.store.feed(1)
            if events:
                event = events[0]
                text += f" · last: {event['actor']} {event['kind']}/{event['action']}: {event['detail']}"
            return truncate(text, max(10, self.size.width - 2))

        def action_filter_text(self) -> None:
            """Prompt for filter text (slash)."""
            self._open_filter_prompt()

        def action_filter_source(self) -> None:
            """Cycle cached provenance filters."""
            index = self.SOURCE_FILTERS.index(self.source_filter)
            self.source_filter = self.SOURCE_FILTERS[(index + 1) % len(self.SOURCE_FILTERS)]
            self.refresh_all(f"source filter: {self.source_filter}")

        def action_clear_filter(self) -> None:
            if len(self.screen_stack) > 1:
                return
            if self.filter_text:
                self.filter_text = ""
                self._pending_note = "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all("filter cleared")
                try:
                    self.query_one("#tree", Tree).focus()
                except Exception:
                    pass
