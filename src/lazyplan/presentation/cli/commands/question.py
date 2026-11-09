"""Question CLI commands."""

from __future__ import annotations

import argparse
import sys
import time

from ....core.entities import PlanQuestion
from ....core.ports.planning import PlanningPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit_read, _emit_record
from ..store import optional_store as _optional_store


def _question_row(question: PlanQuestion) -> str:
    """One porcelain question row."""
    return porcelain.row(
        "question",
        question.id,
        question.status,
        question.text,
        f"plan:{question.plan_id}",
        question.actor,
    )


def _question_text(question: PlanQuestion) -> str:
    """One human question line, including a resolution when present."""
    if question.status != "resolved":
        return f"Q{question.id} [open] {question.text}"
    day = (
        time.strftime("%Y-%m-%d", time.localtime(question.resolved_at))
        if question.resolved_at
        else "-"
    )
    answer = f": {question.resolution}" if question.resolution else ""
    return f"Q{question.id} [resolved {day} @{question.resolved_by}] {question.text}{answer}"


def _cmd_question_add(store: PlanningPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    try:
        question = services.add_question(store, args.plan, args.text, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_record(
        args,
        _question_row(question),
        {"question": to_payload(vars(question))},
    )


def _cmd_question_list(store: PlanningPort | None, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    del actor
    try:
        db = store or _optional_store(args)
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if db is None:
        return _emit_read(args, [], [], "no database")
    plan = db.get_plan(args.plan)
    if plan is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    rows = services.list_questions(db, args.plan, args.status)
    return _emit_read(
        args,
        [to_payload(vars(row)) for row in rows],
        [_question_row(row) for row in rows],
        "\n".join(_question_text(row) for row in rows) or "no questions",
    )


def _cmd_question_resolve(store: PlanningPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    question = services.resolve_question(store, args.id, note=args.note, actor=actor)
    if question is None:
        print(msg_not_found("question", args.id), file=sys.stderr)
        return 1
    return _emit_record(
        args,
        _question_row(question),
        {"question": to_payload(vars(question))},
    )


def _cmd_question_reopen(store: PlanningPort, args: argparse.Namespace, actor: str) -> int:
    from lazyplan import services

    question = services.reopen_question(store, args.id, note=args.note, actor=actor)
    if question is None:
        print(msg_not_found("question", args.id), file=sys.stderr)
        return 1
    return _emit_record(
        args,
        _question_row(question),
        {"question": to_payload(vars(question))},
    )
