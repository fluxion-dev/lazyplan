"""Selection, paging, and display state for the read-only source screen."""

from __future__ import annotations

from dataclasses import dataclass

SourceKey = tuple[str, str, str]


@dataclass
class SourceViewState:
    """Everything the source screen remembers between paints."""

    file_index: int = 0
    view_key: SourceKey | None = None
    page_offset: int = 0
    page_total: int = 0
    page_has_more: bool = False
    split: bool = False
    wrap: bool = True
    fold: bool = True

    def reset_page(self) -> None:
        """Return to the first page of the current diff."""
        self.page_offset = 0
        self.page_total = 0
        self.page_has_more = False

    def cache_key(
        self,
        repo: str,
        sha: str,
        path: str,
        width: int,
        theme: str,
    ) -> tuple[str, str, str, int, str, bool, bool, bool, int]:
        """Cache key for one rendered diff page."""
        return (
            repo,
            sha,
            path,
            width,
            theme,
            self.split,
            self.wrap,
            self.fold,
            self.page_offset,
        )

    def page_label(self, page_lines: int) -> str:
        """A compact ``end/total`` label, empty while everything fits."""
        if self.page_total <= page_lines and not self.page_offset:
            return ""
        end = min(self.page_offset + page_lines, self.page_total)
        return f"{end}/{self.page_total}"
