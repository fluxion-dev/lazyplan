"""Row facts shared by every surface: one value, rendered once.

The CLI text rows, the porcelain rows, and the TUI views format the same
dictionaries. The facts here - which word describes a checkout, which label
identifies an evidence row - are decided once so the surfaces cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: Commits are identified by their first 12 hex digits everywhere.
SHORT_SHA = 12


def short_sha(sha: str) -> str:
    """The canonical short commit id."""
    return sha[:SHORT_SHA]


def branch_word(entry: Mapping[str, Any]) -> str:
    """Branch name, or detached/unknown when the checkout has none."""
    branch = str(entry.get("branch") or "")
    if branch:
        return branch
    return "detached" if entry.get("detached") else "unknown"


def checkout_state(entry: Mapping[str, Any]) -> str:
    """dirty or clean: the one word every surface prints for a work tree."""
    return "dirty" if entry.get("dirty") else "clean"


def stale_word(link: Mapping[str, Any]) -> str:
    """stale when a cached link no longer resolves, else an empty string."""
    return "stale" if link.get("stale") else ""


def evidence_label(row: Mapping[str, Any]) -> str:
    """The first fact an evidence row carries: command, note, or short sha."""
    return (
        str(row.get("command") or "")
        or str(row.get("note") or "")
        or short_sha(str(row.get("commit_sha") or ""))
    )
