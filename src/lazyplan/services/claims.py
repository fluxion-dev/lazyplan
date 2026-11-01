"""Compatibility shim; canonical home is ``lazyplan.services.coordination``."""

from __future__ import annotations

from .coordination import (
    block_task,
    claim_next,
    parse_ttl,
    release_task_claim,
    renew_task_claim,
    start_claim,
    unblock_task,
)

__all__ = [
    "block_task",
    "claim_next",
    "parse_ttl",
    "release_task_claim",
    "renew_task_claim",
    "start_claim",
    "unblock_task",
]
