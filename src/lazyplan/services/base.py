"""Shared service types and constants."""

from __future__ import annotations

import re

ARCHIVE_AFTER_SECS = 24 * 3600
_GATE_PASS = {"pass", "neutral", "skipped"}


class GateError(RuntimeError):
    """A completion gate rejected the finish."""


_LAZYPLAN_TRAILER = re.compile(r"(?i)^lazyplan:\s*(.+)$")
_LAZYPLAN_REF = re.compile(r"(?i)^([ptm])\s*#?(\d+)$")
_LAZYPLAN_BRANCH = re.compile(r"^(task|plan|milestone)/(\d+)(?:-|$)")
_KIND_BY_LETTER = {"p": "plan", "m": "milestone", "t": "task"}
_LETTER_BY_KIND = {"plan": "P", "milestone": "M", "task": "T"}


# -- creation (template fill + auto-criteria live here, not in Store) ------
