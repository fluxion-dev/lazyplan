"""Read packaged agent-facing Markdown files."""

from __future__ import annotations


def data_text(name: str) -> str:
    """Read one packaged agent-facing Markdown file."""
    from importlib.resources import files

    return (files("lazyplan") / "data" / name).read_text(encoding="utf-8")
