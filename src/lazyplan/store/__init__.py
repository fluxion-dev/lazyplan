"""SQLite persistence shared by the TUI and the lpui CLI."""

from __future__ import annotations

from .annotations import AnnotationsMixin
from .base import (
    ClaimConflict,
    ClaimError,
    ClaimMissing,
    StoreBase,
    default_actor,
    to_payload,
)
from .claims import ClaimsMixin
from .links import LinksMixin
from .plans import PlansMixin
from .repos import ReposMixin
from .stubs import CLAIM_DEFAULT_TTL
from .tasks import TasksMixin
from .views import ViewsMixin


class Store(
    PlansMixin,
    ClaimsMixin,
    AnnotationsMixin,
    LinksMixin,
    ReposMixin,
    TasksMixin,
    ViewsMixin,
    StoreBase,
):
    """SQLite persistence shared by the TUI and the lpui CLI."""


__all__ = [
    "CLAIM_DEFAULT_TTL",
    "ClaimConflict",
    "ClaimError",
    "ClaimMissing",
    "Store",
    "default_actor",
    "to_payload",
]
