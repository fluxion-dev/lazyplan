"""System CLI commands."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from lazyplan import services
from lazyplan.services import (
    audit,
    notes,
)

from ....core.ports.insights import InsightsPort
from ...shared import (
    porcelain,
)
from ...shared.design import (
    msg_error,
    msg_not_found,
)
from ..emit import (
    _emit,
)
from ..parser import package_version
from ..rows_proof import (
    _audit_rows,
    _brief_rows,
    _context_rows,
    _trace_rows,
    _trace_text,
)
from ..store import optional_store


def _audit_lines(report: audit.Report) -> list[str]:
    """Plain lines shared by the CLI and tests."""
    window = (
        "all history"
        if not report.since
        else time.strftime("%Y-%m-%d %H:%M", time.localtime(report.since))
    )
    lines = [
        f"plans      {', '.join(f'P{plan}' for plan in report.plans) or '-'}",
        f"window     since {window}",
        f"repos      {len(report.repos)}",
        f"commits    {report.commits_total} total · {report.commits_linked} linked "
        f"· {report.coverage:.0%}",
        f"lag        median {report.median_lag_commits:g} commits · "
        f"{report.median_lag_minutes:g} min ({report.unresolved} unresolved)",
        f"gaps       {len(report.gaps)} open criteria on done rows",
        f"trace      {report.criteria_linked}/{report.criteria_total} criteria "
        f"· {report.trace_coverage:.0%} ({len(report.trace_gaps)} unproven)",
        f"evidence   {report.evidence_covered}/{report.evidence_total} criteria "
        f"· {report.evidence_coverage:.0%}",
    ]
    for gap in report.gaps[:10]:
        lines.append(f"  {gap.kind} #{gap.id}: {gap.text[:60]}")
    for gap in report.trace_gaps[:10]:
        lines.append(f"  unproven criterion #{gap.id}: {gap.text[:60]}")
    return lines


def _audit_output(args: argparse.Namespace, result: audit.Report, reasons: list[str]) -> int:
    """Print the audit in the requested format and apply the strict exit code."""
    strict_fail = 2 if args.strict and reasons else 0
    if args.json:
        payload = result.to_dict()
        payload["breaches"] = reasons
        _emit(args, payload)
        return strict_fail
    if porcelain.enabled(args):
        for line in _audit_rows(result):
            print(line)
        for reason in reasons:
            print(porcelain.row("breach", "-", "-", reason))
        return strict_fail
    for line in _audit_lines(result):
        print(line)
    if args.strict:
        for reason in reasons:
            print(f"strict: {reason}")
        return strict_fail
    return 0


def _cmd_audit(store: InsightsPort | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only accuracy report; --strict exits 2 only on a breach."""
    del actor
    try:
        db = store or optional_store(args)
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"error: cannot read the database: {exc}", file=sys.stderr)
        return 2
    if db is None:
        result = audit.Report(plans=[] if args.plan is None else [args.plan])
    else:
        if args.plan is not None and db.get_plan(args.plan) is None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        since = audit.parse_since(args.since) if args.since else None
        try:
            result = audit.report(
                db,
                [args.plan] if args.plan is not None else None,
                since,
                Path.cwd(),
            )
        except (RuntimeError, OSError, sqlite3.Error) as exc:
            print(f"error: audit unavailable: {exc}", file=sys.stderr)
            return 2
    reasons = audit.Thresholds(
        coverage=args.min_coverage,
        lag_commits=args.max_lag,
        gaps=args.max_gaps,
        trace=args.min_trace,
        evidence=args.min_evidence,
    ).breaches(result)
    return _audit_output(args, result, reasons)


def _cmd_brief(store: InsightsPort | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only session brief; never creates a database."""
    from lazyplan.services import brief

    del actor
    try:
        db = store or optional_store(args)
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"error: cannot read the database: {exc}", file=sys.stderr)
        return 2
    if db is None:
        payload: dict = {"plans": [], "active": 0}
    else:
        if args.plan is not None and db.get_plan(args.plan) is None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        try:
            payload = brief.build(db, args.plan, cwd=Path.cwd())
        except (RuntimeError, OSError, sqlite3.Error) as exc:
            print(f"error: brief unavailable: {exc}", file=sys.stderr)
            return 2
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for line in _brief_rows(db, payload) if db is not None else ():
            print(line)
        return 0
    for line in brief.lines(payload):
        print(line)
    return 0


def _cmd_review(store: InsightsPort | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only deterministic review packet."""
    del actor
    try:
        db = store or optional_store(args)
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"error: cannot read the database: {exc}", file=sys.stderr)
        return 2
    if db is None:
        if args.plan is not None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        print("no active plans")
        return 0
    plan = db.get_plan(args.plan) if args.plan is not None else services.active_plan(db)
    if plan is None:
        if args.plan is not None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        print("no active plans")
        return 0
    packet = services.build_review(
        db,
        plan.id,
        max_chars=args.max_chars,
        cwd=Path.cwd(),
    )
    if packet is None:
        print(msg_not_found("plan", plan.id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(
            args, {"plan": plan.id, "markdown": packet.markdown, "payload": packet.payload}
        )
    if porcelain.enabled(args):
        print(
            porcelain.row(
                "review",
                plan.id,
                plan.status.value,
                plan.name,
                "-",
                len(packet.markdown),
            )
        )
        return 0
    print(packet.markdown, end="")
    return 0


def _cmd_ship(store: InsightsPort | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only deterministic ship note."""
    del actor
    try:
        db = store or optional_store(args)
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"error: cannot read the database: {exc}", file=sys.stderr)
        return 2
    if db is None:
        if args.plan is not None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        print("no active plans")
        return 0
    plan = db.get_plan(args.plan) if args.plan is not None else services.active_plan(db)
    if plan is None:
        if args.plan is not None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        print("no active plans")
        return 0
    note = services.build_ship(db, plan.id, max_chars=args.max_chars, cwd=Path.cwd())
    if note is None:
        print(msg_not_found("plan", plan.id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(args, {"plan": plan.id, "markdown": note.markdown, "payload": note.payload})
    if porcelain.enabled(args):
        payload = note.payload
        tasks = payload.get("tasks", {})
        milestones = payload.get("milestones", [])
        done_milestones = sum(1 for item in milestones if item.get("status") == "done")
        print(
            porcelain.row(
                "ship",
                plan.id,
                plan.status.value,
                f"{done_milestones}/{len(milestones)}",
                f"{tasks.get('done', 0)}/{tasks.get('total', 0)}",
                "-",
            )
        )
        return 0
    print(note.markdown, end="")
    return 0


def _cmd_context(store: InsightsPort | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only session context packet; never creates a database."""
    from lazyplan.services import context

    del actor
    try:
        db = store or optional_store(args)
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"error: cannot read the database: {exc}", file=sys.stderr)
        return 2
    if db is None:
        payload: dict = {"active": 0, "plans": [], "truncated": False}
    else:
        if args.plan is not None and db.get_plan(args.plan) is None:
            print(msg_not_found("plan", args.plan), file=sys.stderr)
            return 1
        try:
            payload = context.build(db, args.plan, max_chars=args.max_chars)
        except ValueError as exc:
            print(msg_error(exc), file=sys.stderr)
            return 2
        except (RuntimeError, OSError, sqlite3.Error) as exc:
            print(f"error: context unavailable: {exc}", file=sys.stderr)
            return 2
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for line in _context_rows(payload):
            print(line)
        return 0
    for line in context.lines(payload):
        print(line)
    return 0


def _cmd_stats(store: InsightsPort, args: argparse.Namespace, actor: str) -> int:
    from ....services import insights

    del actor
    since = audit.parse_since(args.since)
    stale_before = audit.parse_since(args.stale_after)
    if since is None or stale_before is None:
        print(msg_error(ValueError("invalid --since or --stale-after")), file=sys.stderr)
        return 2
    payload = insights.stats.compute(
        store, since, stale_before, actor=getattr(args, "filter_actor", None)
    )
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for key in (
            "wip",
            "cycle_median_minutes",
            "throughput",
            "aging_median_minutes",
            "aging_max_minutes",
            "stale_todos",
            "reopened",
            "claims",
            "blocked",
        ):
            print(porcelain.row("metric", key, "-", payload[key]))
        return 0
    print(f"wip        {payload['wip']} doing")
    print(f"cycle      median {payload['cycle_median_minutes']:g} min")
    print(f"throughput {payload['throughput']} done in window")
    print(
        f"aging      median {payload['aging_median_minutes']:g} min · "
        f"max {payload['aging_max_minutes']:g} min"
    )
    print(f"stale      {payload['stale_todos']} todo past threshold")
    print(f"reopened   {payload['reopened']}")
    print(f"claims     {payload['claims']} active")
    print(f"blocked    {payload['blocked']}")
    return 0


def _cmd_lint(store: InsightsPort, args: argparse.Namespace, actor: str) -> int:
    from ....services import insights

    del actor
    findings = insights.lint.lint_plan(store, args.plan)
    if findings is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    payload = [finding.to_dict() for finding in findings]
    if args.json:
        _emit(args, payload)
    elif porcelain.enabled(args):
        for finding in findings:
            print(
                porcelain.row(
                    "lint",
                    finding.rule,
                    finding.severity,
                    finding.message,
                    f"{finding.kind}:{finding.obj_id}",
                    "-",
                )
            )
    elif findings:
        for finding in findings:
            print(
                f"{finding.severity} {finding.rule} "
                f"{finding.kind} #{finding.obj_id}: {finding.message}"
            )
    else:
        print(f"P{args.plan} lint clean")
    return 2 if args.strict and findings else 0


def _cmd_trace(store: InsightsPort, args: argparse.Namespace, actor: str) -> int:
    from ....services import trace as trace_mod

    del actor
    if args.plan is not None:
        payload = trace_mod.trace_plan(store, args.plan)
    else:
        payload = trace_mod.trace_criterion(store, args.criterion)
    if payload is None:
        kind = "plan" if args.plan is not None else "criterion"
        obj_id = args.plan if args.plan is not None else args.criterion
        print(msg_not_found(kind, obj_id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for line in _trace_rows(payload):
            print(line)
        return 0
    for line in _trace_text(payload):
        print(line)
    return 0


def _cmd_notes(store: object | None, args: argparse.Namespace, actor: str) -> int:
    """Print the changelog sections bundled with this version; needs no database."""
    del store, actor
    installed = package_version()
    try:
        chosen, text = notes.select_notes(
            installed,
            since=args.since or None,
            all_=bool(args.all),
        )
    except (OSError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        return _emit(
            args,
            {
                "installed": installed,
                "versions": [release.as_dict() for release in chosen],
            },
        )
    print(text, end="")
    return 0
