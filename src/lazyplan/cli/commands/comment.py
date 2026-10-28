"""Comment CLI commands."""

from __future__ import annotations

import argparse
import sys
import time

from ... import (
    porcelain,
)
from ...design import (
    msg_not_found,
)
from ...models import Comment
from ...store import Store
from ..emit import (
    _emit,
)


def _comment_result(args: argparse.Namespace, comment: Comment) -> int:
    """Print one comment in JSON, porcelain, or text."""
    if args.json:
        return _emit(args, {"comment": vars(comment)})
    if porcelain.enabled(args):
        print(
            porcelain.comment_row(
                comment.id,
                comment.actor,
                comment.text,
                comment.parent_kind,
                comment.parent_id,
                comment.ts,
                comment.resolved,
            )
        )
    else:
        state = "resolved" if comment.resolved else "open"
        print(f"comment #{comment.id} [{state}] {comment.text}")
    return 0


def _comment_resolve(store: Store, args: argparse.Namespace, actor: str, resolved: bool) -> int:
    if args.comment is None:
        print("error: comment resolve needs --comment ID", file=sys.stderr)
        return 2
    comment = store.resolve_comment(args.comment, resolved=resolved, actor=actor)
    if comment is None:
        print(msg_not_found("comment", args.comment), file=sys.stderr)
        return 1
    return _comment_result(args, comment)


def _comment_scope(store: Store, args: argparse.Namespace) -> int | None:
    """Return an exit code when the comment scope is invalid."""
    if args.kind is None or args.id is None:
        print(f"error: comment {args.action} needs --kind and --id", file=sys.stderr)
        return 2
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    return None


def _comment_add(store: Store, args: argparse.Namespace, actor: str) -> int:
    code = _comment_scope(store, args)
    if code is not None:
        return code
    if args.text is None or not args.text.strip():
        print("error: comment add needs --text", file=sys.stderr)
        return 2
    assert args.kind is not None and args.id is not None
    comment = store.add_comment(args.kind, args.id, args.text, actor=actor)
    return _comment_result(args, comment)


def _comment_list(store: Store, args: argparse.Namespace) -> int:
    code = _comment_scope(store, args)
    if code is not None:
        return code
    assert args.kind is not None and args.id is not None
    comments = store.list_comments(args.kind, args.id, mentions=args.mentions)
    if args.json:
        return _emit(args, [vars(comment) for comment in comments])
    if porcelain.enabled(args):
        for comment in comments:
            print(
                porcelain.comment_row(
                    comment.id,
                    comment.actor,
                    comment.text,
                    comment.parent_kind,
                    comment.parent_id,
                    comment.ts,
                    comment.resolved,
                )
            )
        return 0
    if not comments:
        print("(no comments)")
        return 0
    for comment in comments:
        when = (
            time.strftime("%Y-%m-%d %H:%M", time.localtime(comment.ts)) if comment.ts else "unknown"
        )
        state = "resolved" if comment.resolved else "open"
        print(f"#{comment.id} [{state}] @{comment.actor} {when}: {comment.text}")
    return 0


def _cmd_comment(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.action == "add":
        return _comment_add(store, args, actor)
    if args.action == "list":
        return _comment_list(store, args)
    return _comment_resolve(store, args, actor, args.action == "resolve")


def _cmd_note(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.action == "add":
        if args.text is None or not args.text.strip():
            print("error: note add needs --text", file=sys.stderr)
            return 2
        note = store.add_note(args.kind, args.id, args.text, actor=actor)
        if args.json:
            return _emit(args, {"note": vars(note)})
        if porcelain.enabled(args):
            print(
                porcelain.note_row(
                    note.id, note.actor, note.text, note.parent_kind, note.parent_id, note.ts
                )
            )
        else:
            print(f"noted {args.kind} #{args.id}: {note.text}")
        return 0
    notes = store.list_notes(args.kind, args.id, limit=args.limit)
    if args.json:
        return _emit(args, [vars(n) for n in notes])
    if porcelain.enabled(args):
        for note in notes:
            print(
                porcelain.note_row(
                    note.id, note.actor, note.text, note.parent_kind, note.parent_id, note.ts
                )
            )
        return 0
    if not notes:
        print("(no notes)")
        return 0
    for note in notes:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(note.ts)) if note.ts else "unknown"
        print(f"@{note.actor} {when}: {note.text}")
    return 0
