"""Plan document CLI commands: recipes and atomic apply."""

from __future__ import annotations

import argparse
import sys

from lazyplan.services import drafts as draft_services
from lazyplan.services import plan_apply, plan_document, plan_recipes

from ....core.ports.app import AppPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error
from ..emit import _emit
from .direct import record_direct, refuse_unreasoned
from .drafts import emit_draft


def _cmd_plan_recipe(store: object | None, args: argparse.Namespace, actor: str) -> int:
    """Print one packaged recipe document."""
    del store, actor
    try:
        document = plan_recipes.load(args.name)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit(args, document)


def _cmd_plan_apply(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    """Draft a validated plan document, or create it atomically with --direct."""
    if refuse_unreasoned(args):
        return 2
    try:
        raw = plan_document.load_document(args.file)
        document = plan_document.validate_document(store, raw)
    except (OSError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    counts = plan_document.counts(document)
    if args.dry_run:
        payload = {
            "dry_run": True,
            "created": False,
            **plan_document.preview(document),
            "counts": counts,
        }
        if args.json:
            return _emit(args, payload)
        if porcelain.enabled(args):
            print(
                porcelain.row(
                    "plan",
                    "-",
                    "dry-run",
                    document.title,
                    "-",
                    f"{counts['milestones']}/{counts['tasks']}",
                )
            )
            return 0
        print(
            f"would create {document.title!r}: {counts['milestones']} milestones, "
            f"{counts['tasks']} tasks, {counts['criteria']} criteria"
        )
        return 0
    if not args.direct:
        try:
            draft = draft_services.create(store, raw, actor=actor)
        except ValueError as exc:
            print(msg_error(exc), file=sys.stderr)
            return 2
        return emit_draft(store, args, draft, f"drafted D{draft.id} {draft.title!r} for review")
    try:
        result = plan_apply.apply(store, document, actor=actor)
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    plan = result["plan"]
    if result["created"]:
        record_direct(store, plan.id, actor, args.reason)
    counts = result["counts"]
    payload = {
        "dry_run": False,
        "created": result["created"],
        "plan": to_payload(vars(plan)),
        "counts": counts,
    }
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        print(
            porcelain.plan_row(
                plan.id,
                plan.status.value,
                plan.name,
                f"{counts['milestones']}/{counts['tasks']}",
            )
        )
        return 0
    verb = "created" if result["created"] else "already exists"
    print(
        f"{verb} P{plan.id} {plan.name!r}: {counts['milestones']} milestones, "
        f"{counts['tasks']} tasks, {counts['criteria']} criteria"
    )
    return 0
