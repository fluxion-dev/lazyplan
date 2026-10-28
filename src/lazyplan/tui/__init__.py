"""Textual app package."""

from __future__ import annotations

from .app import _TEXTUAL_OK, run

try:
    from .app import LazyplanApp, create_app
    from .tree import FoldTree
except ImportError:  # pragma: no cover
    pass

__all__ = ["run", "create_app", "LazyplanApp", "FoldTree", "_TEXTUAL_OK"]
