"""Pure view builders for the TUI."""

from __future__ import annotations

from .agents import claim_line, claims_summary, rank_claims
from .control import build_control_strip
from .git import GitDocument, build_git
from .preview import (
    PreviewBlock,
    PreviewDocument,
    build_milestone,
    build_plan,
    build_preview,
    build_task,
)
from .rows import row_text
from .source import (
    DiffPreview,
    commit_label,
    commit_preview,
    file_label,
    file_preview,
    pull_label,
    pull_preview,
    render_diff_preview,
    repo_label,
    repo_preview,
    source_files,
    summary_chips,
)

__all__ = [
    "DiffPreview",
    "GitDocument",
    "PreviewBlock",
    "PreviewDocument",
    "build_control_strip",
    "build_git",
    "build_milestone",
    "build_plan",
    "build_preview",
    "build_task",
    "claims_summary",
    "claim_line",
    "rank_claims",
    "commit_label",
    "commit_preview",
    "file_label",
    "file_preview",
    "pull_label",
    "pull_preview",
    "render_diff_preview",
    "repo_label",
    "repo_preview",
    "row_text",
    "source_files",
    "summary_chips",
]
