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
from .evidence import EvidenceMixin
from .keys import KeysMixin
from .links import LinksMixin
from .plans import PlansMixin
from .proposals import ProposalsMixin
from .questions import QuestionsMixin
from .refs import RefsMixin
from .repos import ReposMixin
from .revisions import RevisionsMixin
from .sessions import SessionsMixin
from .stubs import CLAIM_DEFAULT_TTL
from .tasks import TasksMixin
from .touchpoints import TouchpointsMixin
from .views import ViewsMixin


class Store(
    PlansMixin,
    QuestionsMixin,
    ProposalsMixin,
    RefsMixin,
    SessionsMixin,
    ClaimsMixin,
    EvidenceMixin,
    AnnotationsMixin,
    KeysMixin,
    LinksMixin,
    ReposMixin,
    RevisionsMixin,
    TasksMixin,
    TouchpointsMixin,
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
