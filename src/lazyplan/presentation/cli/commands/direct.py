"""The `--direct` escape that lets a plan skip draft review."""

from __future__ import annotations

import argparse
import sys

from ....core.ports.collaboration import CollaborationPort


def refuse_unreasoned(args: argparse.Namespace) -> bool:
    """Print the error and return True when --direct comes without --reason."""
    if args.direct and not args.reason.strip():
        print("error: --direct needs --reason", file=sys.stderr)
        return True
    return False


def record_direct(store: CollaborationPort, plan_id: int, actor: str, reason: str) -> None:
    """Note on the plan why it skipped draft review."""
    store.add_note(
        "plan", plan_id, f"Skipped draft review ({actor}): {reason.strip()}", actor=actor
    )
