"""Narrow query helpers for optional widgets.

Textual raises ``NoMatches`` and ``TooManyMatches``; the shell uses these
helpers where a missing widget is a normal state (not an error to swallow).
"""

from __future__ import annotations

from typing import TypeVar, cast

from textual.css.query import NoMatches, TooManyMatches
from textual.dom import DOMNode
from textual.widget import Widget

W = TypeVar("W", bound=Widget)


def query_one_opt(
    node: DOMNode,
    selector: str,
    expect_type: type[W] | None = None,
) -> W | None:
    """Return one matching widget, or ``None`` when it is absent or ambiguous."""
    try:
        found = node.query_one(selector)
    except (NoMatches, TooManyMatches):
        return None
    if expect_type is not None and not isinstance(found, expect_type):
        return None
    return cast(W, found)
