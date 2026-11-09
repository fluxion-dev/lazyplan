"""External reference CLI commands."""

from __future__ import annotations

import argparse
import sys

from ....core.entities import ExternalRef
from ....core.ports.refs import RefsPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit_read, _emit_record
from .system import _optional_store


def _ref_row(ref: ExternalRef) -> str:
    """One porcelain reference row."""
    return porcelain.row(
        "ref",
        ref.id,
        ref.provider,
        ref.title or ref.url,
        f"plan:{ref.plan_id}",
        f"{ref.kind} {int(ref.created_at)}",
    )


def _ref_text(ref: ExternalRef) -> str:
    """One human reference line."""
    title = f" {ref.title}" if ref.title else ""
    return f"R{ref.id} {ref.provider}/{ref.kind}{title} {ref.url}"


def _cmd_ref_link(store: RefsPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    try:
        ref = services.link_ref(
            store,
            args.plan,
            args.url,
            provider=args.provider,
            kind=args.type,
            external_id=args.id,
            title=args.title,
            state=args.state,
            actor=actor,
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(args, _ref_row(ref), {"ref": to_payload(vars(ref))})


def _cmd_ref_list(store: RefsPort | None, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    del actor
    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, [], [], "no database")
    if db.get_plan(args.plan) is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    refs = services.list_refs(db, args.plan)
    return _emit_read(
        args,
        [to_payload(vars(ref)) for ref in refs],
        [_ref_row(ref) for ref in refs],
        "\n".join(_ref_text(ref) for ref in refs) or "no references",
    )


def _cmd_ref_unlink(store: RefsPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    if not args.id and not args.url.strip():
        print("error: unlink needs --id or --url", file=sys.stderr)
        return 2
    try:
        removed = services.unlink_ref(store, args.plan, ref_id=args.id, url=args.url, actor=actor)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if not removed:
        print(msg_not_found("reference", args.id or args.url), file=sys.stderr)
        return 1
    return _emit_read(
        args,
        {"plan": args.plan, "removed": args.id or args.url},
        [porcelain.row("ref", args.id or args.url, "removed", args.url, f"plan:{args.plan}", "-")],
        f"removed {args.id or args.url} from P{args.plan}",
    )
