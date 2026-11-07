"""Plan readiness CLI command."""

from __future__ import annotations

import argparse
import sys

from .... import services
from ....store import Store
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit
from .system import _optional_store


def ready_payload(plan_id: int, result: services.ReadyResult) -> dict:
    """JSON payload for one readiness report."""
    return {
        "plan": plan_id,
        "ready": result.ready,
        "checks": [
            {
                "id": check.id,
                "ok": check.ok,
                "detail": check.detail,
                "findings": list(check.findings),
            }
            for check in result.checks
        ],
    }


def ready_text(plan_id: int, result: services.ReadyResult) -> str:
    """Human readiness report."""
    lines = [f"P{plan_id} {'ready' if result.ready else 'not ready'}"]
    for check in result.checks:
        mark = "✓" if check.ok else "✗"
        lines.append(f"  {mark} {check.id}: {check.detail}")
        for finding in check.findings[:3]:
            label = finding.get("text") or finding.get("message") or finding.get("rule") or ""
            lines.append(f"    - {label}")
    return "\n".join(lines)


def ready_rows(result: services.ReadyResult) -> list[str]:
    """Porcelain readiness rows."""
    return [
        porcelain.row(
            "check",
            check.id,
            "pass" if check.ok else "fail",
            check.detail,
            f"plan:{result.plan_id}",
            "-",
        )
        for check in result.checks
    ]


def _cmd_plan_ready(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only plan-ready gate."""
    del actor
    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        print(msg_error(ValueError("no database")), file=sys.stderr)
        return 2
    result = services.plan_ready(db, args.id)
    if result is None:
        print(msg_not_found("plan", args.id), file=sys.stderr)
        return 2
    if args.json:
        _emit(args, ready_payload(args.id, result))
    elif porcelain.enabled(args):
        for line in ready_rows(result):
            print(line)
    else:
        print(ready_text(args.id, result))
    return 0 if result.ready else 1
