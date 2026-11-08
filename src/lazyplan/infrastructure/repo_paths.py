"""Repo path normalization shared by links, claims, and VCS comparisons."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_repo_path(text: str) -> str:
    """Return one absolute, resolved repo path without case folding."""
    raw = str(text).strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    return str(resolved)


def normalize_repo_path(text: str) -> str:
    """Return an absolute, case-folded repo path for equality checks."""
    return os.path.normcase(resolve_repo_path(text))
