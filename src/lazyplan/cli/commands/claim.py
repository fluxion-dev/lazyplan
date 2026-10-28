"""Claim CLI commands."""

from __future__ import annotations

import argparse
import sys
import time

from ... import (
    porcelain,
    services,
)
from ...design import (
    msg_error,
    msg_not_found,
)
from ...store import ClaimConflict, ClaimMissing, Store
from ..emit import (
    _emit,
)


def _expiry_text(expires_at: float, now: float | None = None) -> str:
    """Short human lease state: in 12m, in 2.1h, or expired."""
    stamp = time.time() if now is None else now
    delta = float(expires_at) - stamp
    if delta <= 0:
        return "expired"
    if delta < 3600:
        return f"in {max(1, round(delta / 60))}m"
    if delta < 86400:
        return f"in {delta / 3600:.1f}h"
    return f"in {delta / 86400:.1f}d"


def _cmd_next(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.plan is not None and store.get_plan(args.plan) is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    try:
        result = services.claim_next(
            store,
            actor,
            plan_id=args.plan,
            ttl=args.ttl,
            note=args.note,
            suggest=bool(args.suggest),
        )
    except ClaimConflict as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if result is None:
        if args.json:
            return _emit(args, None)
        if not porcelain.enabled(args):
            print("(no claimable tasks)")
        return 0
    task = result["task"]
    claim = result["claim"]
    if args.json:
        return _emit(args, result)
    if porcelain.enabled(args):
        print(porcelain.task_row(task["id"], task["status"], task["title"], task["milestone_id"]))
        return 0
    if claim is None:
        print(f"next T{task['id']} {task['title']} ({task['status']}) - not claimed")
    else:
        print(
            f"claimed T{task['id']} {task['title']} by {claim['actor']} "
            f"{_expiry_text(claim['expires_at'])}"
        )
    return 0


def _claim_failure(exc: Exception) -> int:
    """Map a lease failure to the agent-readable exit code."""
    if isinstance(exc, (ClaimConflict, ClaimMissing)):
        print(msg_error(exc), file=sys.stderr)
        return 1
    if isinstance(exc, KeyError):
        print(msg_error(ValueError(str(exc))), file=sys.stderr)
        return 1
    print(msg_error(exc), file=sys.stderr)
    return 2


def _claim_take(store: Store, args: argparse.Namespace, actor: str) -> int:
    result = services.start_claim(
        store, args.id, actor, ttl=args.ttl, note=args.note, force=bool(args.force)
    )
    claim = result["claim"]
    task = result["task"]
    if args.json:
        return _emit(args, result)
    if porcelain.enabled(args):
        print(porcelain.claim_row(task["id"], claim["actor"], task["title"], claim["expires_at"]))
    else:
        print(
            f"claimed T{task['id']} {task['title']} by {claim['actor']} "
            f"{_expiry_text(claim['expires_at'])}"
        )
    return 0


def _claim_renew(store: Store, args: argparse.Namespace, actor: str) -> int:
    claim = services.renew_task_claim(store, args.id, actor, ttl=args.ttl)
    task = store.get_task(args.id)
    if args.json:
        return _emit(args, {"claim": vars(claim)})
    if porcelain.enabled(args):
        print(
            porcelain.claim_row(
                claim.task_id,
                claim.actor,
                task.title if task is not None else "-",
                claim.expires_at,
            )
        )
    else:
        print(f"renewed T{claim.task_id} until {_expiry_text(claim.expires_at)}")
    return 0


def _claim_release(store: Store, args: argparse.Namespace, actor: str) -> int:
    result = services.release_task_claim(store, args.id, actor, force=bool(args.force))
    claim = result["claim"]
    task = result["task"]
    if args.json:
        return _emit(args, result)
    if claim is None:
        if not porcelain.enabled(args):
            print(f"T{task['id']} was not claimed")
        return 0
    if porcelain.enabled(args):
        print(porcelain.claim_row(task["id"], claim["actor"], task["title"], None))
    else:
        print(f"released T{task['id']} {task['title']} (was {claim['actor']})")
    return 0


def _cmd_claim(store: Store, args: argparse.Namespace, actor: str) -> int:
    actions = {"take": _claim_take, "renew": _claim_renew, "release": _claim_release}
    try:
        return actions[args.action or "take"](store, args, actor)
    except (ClaimConflict, ClaimMissing, KeyError, ValueError, TypeError) as exc:
        return _claim_failure(exc)


def _cmd_claims(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if getattr(args, "plan", None) is not None and store.get_plan(args.plan) is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    rows = store.list_claims(
        include_expired=bool(getattr(args, "all", False)),
        plan_id=getattr(args, "plan", None),
    )
    if args.json:
        return _emit(args, rows)
    if porcelain.enabled(args):
        for row in rows:
            print(
                porcelain.claim_row(
                    row["task_id"],
                    row["actor"],
                    row["task_title"],
                    row["expires_at"],
                )
            )
        return 0
    if not rows:
        print("(no active claims)" if not getattr(args, "all", False) else "(no claims)")
        return 0
    for row in rows:
        state = "expired" if row["expired"] else _expiry_text(float(row["expires_at"]))
        print(
            f"T{row['task_id']} {row['task_title']} @{row['actor']} {state} ({row['plan_title']})"
        )
    return 0
