"""Compatibility shim; canonical home is ``lazyplan.core.kinds``."""

from __future__ import annotations

from .core.kinds import (
    KIND_ERROR,
    KINDS,
    LABEL_LETTERS,
    MILESTONE,
    PARENT_KIND_ERROR,
    PLAN,
    TABLES,
    TASK,
    check_kind,
    check_parent_kind,
    table_for,
)

__all__ = [
    "KINDS",
    "KIND_ERROR",
    "LABEL_LETTERS",
    "MILESTONE",
    "PARENT_KIND_ERROR",
    "PLAN",
    "TABLES",
    "TASK",
    "check_kind",
    "check_parent_kind",
    "table_for",
]
