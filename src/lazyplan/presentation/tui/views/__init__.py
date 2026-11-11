"""Pure view builders for the TUI."""

from __future__ import annotations

from .agents import rank_sessions, session_line, sessions_summary
from .control import build_control_strip
from .git import GitDocument, build_git
from .preview import (
    PreviewBlock,
    PreviewDocument,
    build_milestone,
    build_plan,
    build_preview,
    build_task,
    common_blocks,
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
    "GitDocument",
    "PreviewBlock",
    "PreviewDocument",
    "build_control_strip",
    "build_git",
    "build_milestone",
    "build_plan",
    "build_preview",
    "build_task",
    "rank_sessions",
    "session_line",
    "sessions_summary",
    "commit_label",
    "commit_preview",
    "file_preview",
    "common_blocks",
    "pull_label",
    "pull_preview",
    "render_diff",
    "repo_label",
    "repo_preview",
    "row_text",
]
