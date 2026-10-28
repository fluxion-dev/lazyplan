"""System CLI commands."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from ... import (
    audit,
    porcelain,
    setup,
)
from ...design import (
    msg_error,
    msg_not_found,
)
from ...repo import find_repo_root, resolve_db_path
from ...setup import layout as setup_layout
from ...setup import ui as setup_ui
from ...store import Store
from ..emit import (
    _emit,
)
from ..parser import package_version
from ..rows_proof import (
    _audit_rows,
    _brief_rows,
    _trace_rows,
    _trace_text,
)


def _setup_interactive(args: argparse.Namespace) -> bool:
    return (
        not getattr(args, "yes", False)
        and not getattr(args, "json", False)
        and not getattr(args, "post_upgrade", False)
        and setup_ui.stdin_tty()
        and sys.stderr.isatty()
    )


def _setup_review(args: argparse.Namespace, home: Path, interactive: bool) -> None:
    findings = setup.detect_findings(Path.cwd(), home, setup.load_state(home))
    if not findings:
        return
    ask = (
        not getattr(args, "json", False)
        and setup_ui.stdin_tty()
        and sys.stderr.isatty()
        and (interactive or bool(getattr(args, "post_upgrade", False)))
    )
    setup.review_findings(
        findings,
        setup.load_state(home),
        home,
        find_repo_root(Path.cwd()),
        read=input,
        write=sys.stderr,
        color=setup_ui.color_enabled(sys.stderr, bool(getattr(args, "json", False))),
        allow_prompt=ask,
        json_mode=bool(getattr(args, "json", False)),
    )


def _print_setup(result: dict) -> None:
    print(f"database:  {result['db']}")
    print(f"templates: {result['templates']}")
    if result["config"]:
        print(f"config:    {result['config']}")
    for skill in result["skills"]:
        print(f"skill:     {skill}")
    for path in result["refreshed"]:
        print(f"refreshed: {path}")
    for path in result.get("backups") or []:
        print(f"backup:    {path}")
    hooks = result.get("hooks") or {}
    for path in hooks.get("installed") or hooks.get("removed") or []:
        print(f"hooks:     {path}")
    for item in hooks.get("skipped") or []:
        print(f"hooks:     skipped {item['path']} ({item['reason']})")
    pointer = result.get("agents_pointer") or {}
    if pointer.get("path"):
        print(f"pointer:   {pointer['path']} ({pointer['status']})")
    print(f"state:     {result['state']}")


def _cmd_setup(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Re-run setup, or apply remembered choices without prompts."""
    from ... import hook_install

    del store, actor
    home = Path.home()
    state = setup.load_state(home)
    version = package_version()
    interactive = _setup_interactive(args)
    if interactive:
        initial = setup.choice_from_args(args, Path.cwd(), home, state)
        result = setup.run_wizard(
            Path.cwd(),
            home,
            state,
            version,
            initial=initial,
            hooks_enabled=getattr(args, "hooks", None),
        )
        if result is None:
            return _emit(args, {"cancelled": True}) if getattr(args, "json", False) else 0
    else:
        choice = setup.choice_from_args(args, Path.cwd(), home, state)
        result = setup.apply_choice(choice, find_repo_root(Path.cwd()), home, version)
    root = find_repo_root(Path.cwd())
    setup.install_integrations(
        result,
        home,
        root,
        getattr(args, "hooks", None),
        getattr(args, "agents_pointer", None),
    )
    if result.get("placement") == setup.HOME:
        _setup_review(args, home, interactive)
    if result.get("wizard") and not getattr(args, "json", False):
        selected = [h for h in (result.get("agents") or []) if h in hook_install.HOSTS]
        plugins = (
            [spec.path for spec in hook_install.preview(home, selected)]
            if getattr(args, "hooks", None) is not False
            else []
        )
        backups = [Path(path) for path in result.get("hooks", {}).get("backups") or []]
        setup_ui.success(
            sys.stderr,
            Path(result["db"]),
            [Path(path) for path in result["skills"]],
            backups,
            setup_ui.color_enabled(sys.stderr, False),
            plugins,
        )
        return 0
    if getattr(args, "json", False):
        return _emit(args, result)
    _print_setup(result)
    return 0


def _doctor_data(
    args: argparse.Namespace, home: Path, state: setup.SetupState
) -> tuple[setup_layout.SetupLayout, list[Path], dict]:
    choice = setup.choice_from_args(args, Path.cwd(), home, state)
    root = find_repo_root(Path.cwd())
    layout, skill_files = setup.preview(choice, root, home)
    report = setup_layout.inventory(layout)
    report["findings"] = [
        {"kind": f.kind, "path": str(f.path), "state": f.state, "detail": f.detail}
        for f in setup.detect_findings(Path.cwd(), home, state)
    ]
    missing_hooks = [path for path in state.hook_files if not Path(path).is_file()]
    report["hooks"] = {
        "enabled": state.hooks,
        "files": list(state.hook_files),
        "missing": missing_hooks,
    }
    report["state"] = state.to_dict()
    report["skills"] = [str(path) for path in skill_files]
    issues = bool(report["findings"]) or bool(missing_hooks)
    issues = issues or (state.hooks and not state.hook_files)
    issues = issues or state.version != setup.SETUP_VERSION
    report["clean"] = bool(report["clean"] and not issues)
    return layout, skill_files, report


def _print_doctor(layout: setup_layout.SetupLayout, skill_files: list[Path], report: dict) -> None:
    print(f"database:  {layout.db}")
    print(f"templates: {layout.templates_dir}")
    print(f"config:    {layout.config or '-'}")
    for skill in skill_files:
        print(f"skill:     {skill}")
    hooks = report["hooks"]
    print(f"hooks:     {'enabled' if hooks['enabled'] else 'none'}")
    for path in hooks["files"]:
        print(f"hook:      {path}")
    for path in hooks["missing"]:
        print(f"hook miss: {path}")
    print(f"clean:     {'yes' if report['clean'] else 'no'}")
    for item in report["misplaced"]:
        print(f"misplaced: {item}")
    for item in report["missing"]:
        print(f"missing:   {item}")
    for finding in report["findings"]:
        print(f"finding:   {finding['kind']} {finding['path']} ({finding['state']})")
    for note in report["notes"]:
        print(f"note:      {note}")


def _cmd_doctor(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only setup report; never opens or writes a database."""
    del store, actor
    home = Path.home()
    state = setup.load_state(home)
    layout, skill_files, report = _doctor_data(args, home, state)
    code = 0 if report["clean"] else 1
    if getattr(args, "json", False):
        _emit(args, report)
        return code
    _print_doctor(layout, skill_files, report)
    return code


def _optional_store(args: argparse.Namespace) -> Store | None:
    """Open an existing database without creating one."""
    path = Path(resolve_db_path(args.db)).expanduser()
    if not path.is_file():
        return None
    return Store(str(path))


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


def _cmd_audit(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only accuracy report; --strict exits 2 only on a breach."""
    del actor
    try:
        db = store or _optional_store(args)
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
    ).breaches(result)
    return _audit_output(args, result, reasons)


def _cmd_brief(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only session brief; never creates a database."""
    from ... import brief

    del actor
    try:
        db = store or _optional_store(args)
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


def _cmd_stats(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import stats as stats_mod

    del actor
    since = audit.parse_since(args.since)
    stale_before = audit.parse_since(args.stale_after)
    if since is None or stale_before is None:
        print(msg_error(ValueError("invalid --since or --stale-after")), file=sys.stderr)
        return 2
    payload = stats_mod.compute(
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


def _cmd_lint(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import lint as lint_mod

    del actor
    findings = lint_mod.lint_plan(store, args.plan)
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


def _cmd_trace(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import trace as trace_mod

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
