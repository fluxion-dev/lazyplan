"""Shared access to the built landing page."""

from __future__ import annotations

from tests.support.paths import ROOT

DIST = ROOT / "site" / "dist" / "index.html"


def has_built_site() -> bool:
    """Return True when the site build output exists."""
    return DIST.is_file()


def page_html() -> str:
    """Return the prerendered landing page."""
    return DIST.read_text(encoding="utf-8")
