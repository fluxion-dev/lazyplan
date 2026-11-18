"""Draft CLI commands: create, review, annotate, revise, and promote."""

from __future__ import annotations

import argparse
import json
import sys

from lazyplan.services import drafts as draft_services
from lazyplan.services import plan_document

from ....core.entities import DraftAnnotation, PlanDraft
from ....core.ports.app import AppPort
from ....core.serialization import to_payload
from ...shared import porcelain
from ...shared.design import msg_error, msg_not_found
from ..emit import _emit, _emit_read


def _draft_payload(draft: PlanDraft, open_count: int, total_count: int) -> dict:
    """JSON fields for one draft plus its annotation counts."""
    payload = to_payload(vars(draft))
    payload["open_annotations"] = open_count
    payload["total_annotations"] = total_count
    return payload


def _draft_row(draft: PlanDraft, open_count: int, total_count: int) -> str:
    """One porcelain draft row."""
    return porcelain.draft_row(
        draft.id,
        draft.status,
        draft.title,
        draft.plan_id,
        draft.revision,
        open_count,
        total_count,
    )


def _draft_text(draft: PlanDraft, open_count: int, total_count: int) -> str:
    """One human draft line."""
    target = f" -> P{draft.plan_id}" if draft.plan_id else ""
    return (
        f"D{draft.id} [{draft.status} r{draft.revision}] {draft.title}"
        f" · {open_count}/{total_count} open{target}"
    )


def _annotation_row(annotation: DraftAnnotation) -> str:
    """One porcelain annotation row."""
    return porcelain.annotation_row(
        annotation.id,
        annotation.status,
        annotation.body,
        annotation.draft_id,
        annotation.kind,
        annotation.block_key,
        annotation.anchor_state,
    )


def _annotation_text(annotation: DraftAnnotation) -> str:
    """One human annotation line, including quote and response."""
    quote = f' "{annotation.quote}"' if annotation.quote else ""
    line = (
        f"A{annotation.id} [{annotation.status} {annotation.kind}]"
        f" {annotation.block_key}{quote} ({annotation.anchor_state}): {annotation.body}"
    )
    if annotation.response:
        line += f"\n  response: {annotation.response}"
    return line


def _write(args: argparse.Namespace, line: str, payload: object, text: str) -> int:
    """JSON, porcelain, or human confirmation for one write."""
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        print(line)
        return 0
    print(text)
    return 0


def _emit_draft(store: AppPort, args: argparse.Namespace, draft: PlanDraft, text: str) -> int:
    """Emit one changed draft in the requested mode."""
    open_count, total_count = draft_services.annotation_counts(store, draft.id)
    payload = {"draft": _draft_payload(draft, open_count, total_count)}
    return _write(args, _draft_row(draft, open_count, total_count), payload, text)


def _emit_annotation(args: argparse.Namespace, annotation: DraftAnnotation, text: str) -> int:
    """Emit one changed annotation in the requested mode."""
    payload = {"annotation": to_payload(vars(annotation))}
    return _write(args, _annotation_row(annotation), payload, text)


def _show_text(detail: draft_services.DraftDetail) -> str:
    """Render one draft, its blocks, and its annotations as plain text."""
    lines = [
        _draft_text(
            detail.draft,
            detail.open_annotations,
            detail.total_annotations,
        )
    ]
    for block in detail.blocks:
        indent = "  " * block.level
        lines.append(f"{indent}{block.label} [{block.kind}]")
        lines.extend(f"{indent}  {line}" for line in block.text.splitlines())
    lines.append("")
    lines.append("annotations:")
    if detail.annotations:
        lines.extend(_annotation_text(row) for row in detail.annotations)
    else:
        lines.append("none")
    return "\n".join(lines)


def _cmd_draft_list(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    del actor
    rows = draft_services.list_drafts(store, args.status)
    counts = draft_services.annotation_counts_map(store)
    payload = []
    porcelain_lines = []
    text_lines = []
    for draft in rows:
        open_count, total_count = counts.get(draft.id, (0, 0))
        payload.append(_draft_payload(draft, open_count, total_count))
        porcelain_lines.append(_draft_row(draft, open_count, total_count))
        text_lines.append(_draft_text(draft, open_count, total_count))
    return _emit_read(args, payload, porcelain_lines, "\n".join(text_lines) or "no drafts")


def _cmd_draft_show(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        detail = draft_services.detail(store, args.id)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    draft = detail.draft
    payload = {
        "draft": _draft_payload(draft, detail.open_annotations, detail.total_annotations),
        "document": json.loads(draft.document),
        "blocks": [vars(block) for block in detail.blocks],
        "annotations": [to_payload(vars(row)) for row in detail.annotations],
    }
    porcelain_lines = [_draft_row(draft, detail.open_annotations, detail.total_annotations)]
    porcelain_lines.extend(
        porcelain.block_row(block.key, block.kind, block.label, draft.id, block.level)
        for block in detail.blocks
    )
    porcelain_lines.extend(_annotation_row(row) for row in detail.annotations)
    return _emit_read(args, payload, porcelain_lines, _show_text(detail))


def _cmd_draft_annotations(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    del actor
    try:
        rows = draft_services.list_annotations(store, args.id, args.status)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    return _emit_read(
        args,
        [to_payload(vars(row)) for row in rows],
        [_annotation_row(row) for row in rows],
        "\n".join(_annotation_text(row) for row in rows) or "no annotations",
    )


def _cmd_draft_add(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        raw = plan_document.load_document(args.file)
        draft = draft_services.create(store, raw, actor=actor)
    except (OSError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_draft(store, args, draft, f"created D{draft.id} {draft.title!r}")


def _cmd_draft_revise(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        raw = plan_document.load_document(args.file)
        draft = draft_services.revise(
            store,
            args.id,
            raw,
            args.base_revision,
            actor=actor,
            note=args.note,
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_draft(
        store,
        args,
        draft,
        f"revised D{draft.id} to r{draft.revision}",
    )


def _cmd_draft_submit(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        draft = draft_services.submit(store, args.id, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_draft(store, args, draft, f"submitted D{draft.id} for revision")


def _cmd_draft_ready(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        draft = draft_services.ready(store, args.id, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_draft(store, args, draft, f"D{draft.id} is ready for review")


def _cmd_draft_annotate(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        annotation = draft_services.annotate(
            store,
            args.id,
            args.block,
            args.kind,
            args.text,
            quote=args.quote,
            start_offset=args.start,
            end_offset=args.end,
            author=actor,
        )
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_annotation(
        args,
        annotation,
        f"annotated {annotation.block_key} as A{annotation.id}",
    )


def _cmd_draft_respond(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        annotation = draft_services.respond(store, args.id, args.response, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_annotation(args, annotation, f"responded to A{annotation.id}")


def _cmd_draft_resolve(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        annotation = draft_services.resolve(store, args.id, args.response, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_annotation(args, annotation, f"resolved A{annotation.id}")


def _cmd_draft_dismiss(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        annotation = draft_services.dismiss(store, args.id, args.reason, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit_annotation(args, annotation, f"dismissed A{annotation.id}")


def _cmd_draft_promote(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        promotion = draft_services.promote(store, args.id, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    plan = promotion.plan
    open_count, total_count = draft_services.annotation_counts(store, promotion.draft.id)
    payload = {
        "draft": _draft_payload(promotion.draft, open_count, total_count),
        "plan": to_payload(vars(plan)),
        "created": promotion.created,
        "counts": promotion.counts,
    }
    line = porcelain.plan_row(
        plan.id,
        plan.status.value,
        plan.name,
        f"{promotion.counts['milestones']}/{promotion.counts['tasks']}",
    )
    if promotion.created:
        text = f"created P{plan.id} {plan.name!r} from D{promotion.draft.id}"
    else:
        text = f"D{promotion.draft.id} already promoted to P{plan.id}"
    return _write(args, line, payload, text)


def _cmd_draft_delete(store: AppPort, args: argparse.Namespace, actor: str) -> int:
    try:
        removed = draft_services.delete_draft(store, args.id, actor=actor)
    except KeyError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if not removed:
        print(msg_not_found("draft", args.id), file=sys.stderr)
        return 1
    line = porcelain.row("draft", args.id, "deleted", "-", "-", "-")
    payload = {"ok": True, "deleted": f"draft #{args.id}"}
    return _write(args, line, payload, f"deleted D{args.id}")
