"""Porcelain output: stable tab-separated records for active agents.

Rows are one line, no header, no glyphs, no ANSI, and no blank lines:

    kind<TAB>id<TAB>status<TAB>title<TAB>parent<TAB>extra

`parent` is `-` or `kind:id` (for example `plan:12`). `extra` is progress
(`done/total`) for plans and milestones and `-` for every other row.
Criterion rows use `kind=criterion`, status `open|done`, and parent
`kind:id`. Text fields never carry a tab or newline: separators become a
single space, so every record stays parseable with `line.split("\\t")`.

Enable with `--porcelain` (before or after the verb) or
`LAZYPLAN_PORCELAIN=1`. `--json` always wins when both are present, so the
full-fidelity escape hatch stays unambiguous.

Pure formatting only: this module never reads the store and never imports
Textual, so the CLI path stays fast and dependency-free.
"""

from __future__ import annotations

import os
import re
from typing import Any

ENV = "LAZYPLAN_PORCELAIN"
_TRUE = {"1", "true", "yes", "on"}
_SEPARATORS = re.compile(r"[\t\r\n]+")


def env_enabled(value: str | None = None) -> bool:
    """True when the value (or the environment switch) asks for porcelain."""
    raw = os.environ.get(ENV, "") if value is None else value
    return raw.strip().lower() in _TRUE


def enabled(args: Any) -> bool:
    """Porcelain is on unless JSON asked for full fidelity."""
    if getattr(args, "json", False):
        return False
    if getattr(args, "porcelain", False):
        return True
    return env_enabled()


def clean(value: Any) -> str:
    """Flatten tabs, carriage returns, and newlines so one record stays one line."""
    text = "" if value is None else str(value)
    return _SEPARATORS.sub(" ", text).strip()


def field(value: Any) -> str:
    """A non-empty row field; missing values use the documented dash."""
    return clean(value) or "-"


def row(
    kind: Any,
    obj_id: Any,
    status: Any,
    title: Any,
    parent: Any = "-",
    extra: Any = "-",
) -> str:
    """Render one porcelain record in the documented six-column order."""
    return "\t".join(
        (
            field(kind),
            field(obj_id),
            field(status),
            field(title),
            field(parent),
            field(extra),
        )
    )
