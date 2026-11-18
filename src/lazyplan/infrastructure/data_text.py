"""Read packaged agent-facing files (Markdown, JSON, or HTML)."""

from __future__ import annotations


def data_text(name: str) -> str:
    """Read one packaged agent-facing file as UTF-8 text."""
    from importlib.resources import files

    return (files("lazyplan") / "data" / name).read_text(encoding="utf-8")
