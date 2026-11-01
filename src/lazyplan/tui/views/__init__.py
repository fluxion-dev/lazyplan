"""Pure view builders for the TUI."""

from __future__ import annotations

from .bars import status_bar
from .detail import DetailDocument, build_detail, detail_breadcrumb, detail_object
from .preview import (
    PreviewBlock,
    PreviewDocument,
    build_milestone,
    build_plan,
    build_preview,
    build_task,
    common_blocks,
    common_lines,
    render_blocks,
)
from .rows import row_text
from .source import (
    commit_label,
    commit_preview,
    file_preview,
    pull_label,
    pull_preview,
    render_diff,
    repo_label,
    repo_preview,
)

__all__ = [
    "DetailDocument",
    "PreviewBlock",
    "PreviewDocument",
    "build_milestone",
    "build_plan",
    "build_preview",
    "build_detail",
    "build_task",
    "commit_label",
    "commit_preview",
    "file_preview",
    "common_blocks",
    "common_lines",
    "detail_breadcrumb",
    "detail_object",
    "pull_label",
    "pull_preview",
    "render_blocks",
    "render_diff",
    "repo_label",
    "repo_preview",
    "row_text",
    "status_bar",
]
