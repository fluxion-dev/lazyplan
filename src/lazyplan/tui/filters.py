"""Textual app: filters."""

from __future__ import annotations

try:
    from rich.text import Text
    from textual.widgets import Label, Tree

    from .query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from .. import stats as stats_mod
from ..repo import repo_label
from .base import AppBase
from .constants import STATUS_CYCLE
from .screens import (
    FilterPromptScreen,
)
from .views.bars import status_bar

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
            label = query_one_opt(self, "#status", Label)
            if label is not None:
                label.update(self._status_text(self.store.counts(), note))

        def _status_text(self, counts: dict[str, int], note: str) -> Text:
            """Human counts, filter state, update notice, and the latest event."""
            open_tasks = counts["tasks"] - counts["tasks_done"]
            update = ""
            if self._update_notice is not None:
                update = (
                    f"update v{self._update_latest}" if self._update_latest else "update available"
                )
            events = self.store.feed(1)
            event = ""
            if events:
                latest = events[0]
                event = f"{latest['actor']} {latest['kind']}/{latest['action']}: {latest['detail']}"
            return status_bar(
                repo=repo_label(self.store.path),
                plans=counts["plans"],
                open_tasks=open_tasks,
                doing=counts["plans_doing"],
                attention=len(stats_mod.attention_ids(self.store)),
                marked=len(self.marked),
                status=self.status_filter.value if self.status_filter is not None else "",
                source=self.source_filter if self.source_filter != "all" else "",
                filter_text=self.filter_text.strip(),
                recent=None if self.show_all else services.DEFAULT_PLAN_LIMIT,
                update=update,
                note=note,
                event=event,
                width=max(10, self.size.width - 2),
            )

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
                tree = query_one_opt(self, "#tree", Tree)
                if tree is not None:
                    tree.focus()
