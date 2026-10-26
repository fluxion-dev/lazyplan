"""`lpui` companion CLI (`lazyplan` is the same binary). Human + agent ingress:
every mutation writes SQLite; the running TUI auto-refreshes. Stdlib only
(no Textual import here)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from . import (
    audit,
    brief,
    hook_hosts,
    hook_install,
    hooks,
    porcelain,
    services,
    setup,
    setup_layout,
    setup_ui,
)
from . import issues as issues_mod
from . import lint as lint_mod
from . import mcp as mcp_mod
from . import share as share_mod
from . import stats as stats_mod
from . import sync as sync_mod
from . import trace as trace_mod
from .cli_parser import build_parser, package_version
from .design import (
    EMPTY_COMMITS,
    EMPTY_FEED,
    EMPTY_NO_PLANS,
    HELP_TEXT,
    msg_error,
    msg_no_head,
    msg_no_vcs,
    msg_not_found,
)
from .forge import RepoRef, parse_pull_url, resolve_auth
from .github import GitHubClient, GitHubError
from .models import Comment, Criterion, Milestone, Plan, Status, Task
from .render import (
    render_commits,
    render_forge_links,
    render_forge_status,
    render_full,
    render_git_status,
    render_markdown,
    summary_lines,
    tree_lines,
)
from .repo import find_repo_root, repo_label, resolve_db_path
from .seed import seed as seed_demo
from .store import ClaimConflict, ClaimMissing, Store, _ser
from .upgrade import (
    NOTICE_TIMEOUT,
    UpgradeError,
    detect,
    guard_message,
    latest_version,
    notice_text,
    parse_version,
    run_upgrade,
)
from .vcs import detect_backend, origin_url


def _emit(args: argparse.Namespace, payload: object) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _emit_record(args: argparse.Namespace, line: str, payload: object) -> int:
    """Porcelain prints one record; every other mode keeps the existing emitter."""
    if porcelain.enabled(args):
        print(line)
        return 0
    return _emit(args, payload)


def _emit_read(
    args: argparse.Namespace,
    payload: object,
    porcelain_lines: list[str],
    text: str,
    empty: str = "",
) -> int:
    """Pick JSON, porcelain rows, or human text for one read command."""
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        for line in porcelain_lines:
            print(line)
        return 0
    print(text if text else empty)
    return 0


def _progress(store: Store, plan_id: int | None = None, milestone_id: int | None = None) -> str:
    """Task progress for a plan or milestone as `done/total`."""
    if milestone_id is not None:
        tasks = store.list_tasks(milestone_id)
    else:
        tasks = [
            task
            for milestone in store.list_milestones(plan_id or 0)
            for task in store.list_tasks(milestone.id)
        ]
    done = sum(1 for task in tasks if task.status == Status.DONE)
    return f"{done}/{len(tasks)}"


def _porcelain_row(store: Store, obj: Plan | Milestone | Task) -> str:
    """One row for a plan, milestone, or task using its inherited parent id."""
    if isinstance(obj, Plan):
        return porcelain.plan_row(
            obj.id, obj.status.value, obj.name, _progress(store, plan_id=obj.id)
        )
    if isinstance(obj, Milestone):
        return porcelain.milestone_row(
            obj.id,
            obj.status.value,
            obj.title,
            obj.plan_id,
            _progress(store, milestone_id=obj.id),
        )
    return porcelain.task_row(
        obj.id,
        obj.status.value,
        obj.title,
        obj.milestone_id,
        "blocked" if obj.blocked else "-",
    )


def _criterion_row(criteria: Criterion) -> str:
    """One criterion row with its parent kind and id."""
    return porcelain.row(
        "criterion",
        criteria.id,
        "done" if criteria.done else "open",
        criteria.text,
        f"{criteria.parent_kind}:{criteria.parent_id}",
        "-",
    )


def _tty_dot(args: argparse.Namespace) -> str:
    """ANSI dots on a tty; plain for pipes, --json, and porcelain."""
    if getattr(args, "json", False) or porcelain.enabled(args):
        return "plain"
    return "ansi" if sys.stdout.isatty() else "plain"


def _resolve_title(args: argparse.Namespace) -> str:
    """--title wins, --name is the legacy alias."""
    if getattr(args, "title", None):
        return str(args.title)
    if getattr(args, "name", None):
        return str(args.name)
    return ""


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


def _trace_entries(payload: dict) -> list[dict]:
    """Normalize a plan or criterion trace payload to criterion entries."""
    if "criteria" in payload:
        return list(payload["criteria"])
    return [{"criterion": payload["criterion"], "tasks": payload.get("tasks", [])}]


def _trace_text(payload: dict) -> list[str]:
    """Human trace: criterion, proving tasks, commits, and PRs."""
    lines: list[str] = []
    if "plan" in payload:
        plan = payload["plan"]
        lines.append(f"P{plan['id']} {plan['name']} ({plan['status']})")
    for entry in _trace_entries(payload):
        crit = entry["criterion"]
        state = "done" if crit.get("done") else "open"
        lines.append(
            f"criterion #{crit['id']} [{state}] {crit['text']} "
            f"({crit['parent_kind']} #{crit['parent_id']})"
        )
        tasks = entry.get("tasks", [])
        if not tasks:
            lines.append("  (no proving task)")
            continue
        for item in tasks:
            task = item["task"]
            lines.append(f"  T{task['id']} {task['title']} (M{task['milestone_id']})")
            for commit in item.get("commits", []):
                lines.append(f"    {str(commit.get('sha', ''))[:12]} {commit.get('subject', '')}")
            for pull in item.get("forge_links", []):
                lines.append(
                    f"    PR #{pull.get('number')} {pull.get('state') or 'unknown'} "
                    f"{pull.get('title', '')}"
                )
    return lines


def _trace_rows(payload: dict) -> list[str]:
    """Porcelain trace rows: criteria, criterion-task edges, commits, and PRs."""
    rows: list[str] = []
    if "plan" in payload:
        plan = payload["plan"]
        rows.append(porcelain.plan_row(plan["id"], plan["status"], plan["name"]))
    for entry in _trace_entries(payload):
        crit = entry["criterion"]
        rows.append(
            porcelain.row(
                "criterion",
                crit["id"],
                "done" if crit.get("done") else "open",
                crit.get("text"),
                f"{crit['parent_kind']}:{crit['parent_id']}",
                "-",
            )
        )
        tasks = entry.get("tasks", [])
        if not tasks:
            rows.append(
                porcelain.row(
                    "trace",
                    crit["id"],
                    "missing",
                    "-",
                    f"criterion:{crit['id']}",
                    "-",
                )
            )
        for item in tasks:
            task = item["task"]
            rows.append(
                porcelain.row(
                    "trace",
                    crit["id"],
                    "proves",
                    task.get("title"),
                    f"criterion:{crit['id']}",
                    f"task:{task['id']}",
                )
            )
            rows.extend(_issue_dict_rows(item.get("issues", [])))
            for commit in item.get("commits", []):
                rows.append(_commit_row(commit, f"task:{task['id']}"))
            for pull in item.get("forge_links", []):
                rows.append(_pr_row(pull, f"task:{task['id']}"))
    return rows


def _cmd_trace(store: Store, args: argparse.Namespace, actor: str) -> int:
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


def _cmd_sync(store: Store, args: argparse.Namespace, actor: str) -> int:
    try:
        data = json.loads(Path(args.file).read_text())
        report = sync_mod.sync(store, data, actor=actor, dry_run=bool(args.dry_run))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit(args, report)
    elif porcelain.enabled(args):
        for item in report["added"]:
            print(porcelain.row("sync", item["uid"] or "-", "add", item["title"], "-", "added"))
        for item in report["skipped"]:
            print(
                porcelain.row(
                    "sync",
                    item["uid"] or "-",
                    "skip",
                    item["title"],
                    f"plan:{item['local_id']}",
                    "identical",
                )
            )
        for item in report["conflicts"]:
            print(
                porcelain.row(
                    "sync",
                    item["uid"] or "-",
                    "conflict",
                    item["title"],
                    f"plan:{item['local_id']}" if item["local_id"] else "-",
                    ",".join(item["differences"]),
                )
            )
    else:
        print(
            f"{'dry-run: ' if report['dry_run'] else ''}"
            f"{len(report['added'])} added · {len(report['skipped'])} skipped · "
            f"{len(report['conflicts'])} conflicts"
        )
        for item in report["conflicts"]:
            print(
                f"  conflict {item['title']} ({item['uid'] or '-'}): "
                f"{', '.join(item['differences'])}"
            )
    return 1 if report["conflicts"] else 0


def _cmd_share(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if store.get_plan(args.plan) is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    text = share_mod.write(store, args.plan, args.format, args.out)
    if text is None:
        print(msg_not_found("plan", args.plan), file=sys.stderr)
        return 1
    if args.out:
        if args.json:
            return _emit(args, {"shared": args.out, "format": args.format})
        print(f"shared P{args.plan} as {args.format}: {args.out}")
        return 0
    print(text, end="" if text.endswith("\n") else "\n")
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


def _cmd_mcp(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    del store
    path = resolve_db_path(args.db)
    return mcp_mod.run(str(path), actor=actor, read_only=bool(args.read_only))


def _cmd_hook(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only lifecycle reminder; always exits 0 so a host never blocks."""
    del store, actor
    payload = hooks.read_payload(sys.stdin)
    host = hooks.detect_host(payload, args.host)
    result = hooks.run(args.event, payload, host, Path.cwd())
    if args.json:
        _emit(
            args,
            {
                "event": args.event,
                "host": host,
                "text": result.text,
                "context": result.context,
            },
        )
        return 0
    rendered = hook_hosts.render(host, args.event, result)
    if rendered:
        print(rendered)
    return 0


def _cmd_info(store: Store, args: argparse.Namespace, actor: str) -> int:
    root = find_repo_root(Path.cwd())
    plan_dir = store.path.parent
    try:
        contents = sorted(f.name for f in plan_dir.iterdir()) if plan_dir.is_dir() else []
    except OSError:
        contents = []
    payload = {
        "db": str(store.path),
        "repo": str(root) if root else None,
        "scope": repo_label(store.path),
        "plan_files": contents,
        "counts": store.counts(),
    }
    if porcelain.enabled(args):
        for line in _info_rows(payload):
            print(line)
        return 0
    return _emit(args, payload)


def _cmd_seed(store: Store, args: argparse.Namespace, actor: str) -> int:
    seed_demo(store)
    return _emit(args, {"db": str(store.path), "counts": store.counts()})


def _list_filters(args: argparse.Namespace) -> tuple[str, Status | None]:
    """Translate --archived/--status into service filters."""
    if args.archived:
        return "only", None
    if args.status is None:
        return "hide", None
    if args.status == "all":
        return "show", None
    return "hide", Status(args.status)


def _list_limit(args: argparse.Namespace) -> int | None:
    """Default text lists cap plans; explicit rows, --all, and JSON do not."""
    if args.plan is not None or args.all:
        return None
    if args.json:
        return int(args.limit) if args.limit is not None else None
    return int(args.limit) if args.limit is not None else services.DEFAULT_PLAN_LIMIT


def _list_payload(
    store: Store,
    status: Status | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone: int | None,
    plan_id: int | None,
) -> list[dict]:
    """Full JSON tree; shape stays stable for scripts."""
    return [
        {
            "plan": _ser(vars(plan)),
            "criteria": [vars(c) for c in store.list_criteria("plan", plan.id)],
            "links": [vars(c) for c in store.list_links("plan", plan.id)],
            "repos": store.list_repos("plan", plan.id),
            "effective_repos": store.effective_repos("plan", plan.id),
            "milestones": [
                {
                    "milestone": _ser(vars(s)),
                    "criteria": [vars(c) for c in store.list_criteria("milestone", s.id)],
                    "links": [vars(c) for c in store.list_links("milestone", s.id)],
                    "repos": store.list_repos("milestone", s.id),
                    "effective_repos": store.effective_repos("milestone", s.id),
                    "tasks": [
                        {
                            "task": _ser(vars(t)),
                            "criteria": [vars(c) for c in store.list_criteria("task", t.id)],
                            "links": [vars(c) for c in store.list_links("task", t.id)],
                            "repos": store.list_repos("task", t.id),
                            "effective_repos": store.effective_repos("task", t.id),
                        }
                        for t in tasks
                    ],
                }
                for s, tasks in milestones
            ],
        }
        for plan, milestones in services.tree(
            store,
            status=status,
            plan_id=plan_id,
            archived=archived,
            limit=limit,
            repo=repo,
            milestone_id=milestone,
        )
    ]


def _list_lines(
    store: Store,
    args: argparse.Namespace,
    status: Status | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone: int | None,
) -> list[str]:
    """Summary by default; --tree (or a milestone filter) shows hierarchy."""
    dot = _tty_dot(args)
    if getattr(args, "tree", False) or milestone is not None:
        return tree_lines(
            store,
            status,
            args.plan,
            dot=dot,
            archived=archived,
            limit=limit,
            repo=repo,
            milestone_id=milestone,
        )
    return summary_lines(
        store,
        status,
        args.plan,
        dot=dot,
        archived=archived,
        limit=limit,
        repo=repo,
    )


def _porcelain_list_lines(
    store: Store,
    status: Status | None,
    plan_id: int | None,
    archived: str,
    limit: int | None,
    repo: str | None,
    milestone_id: int | None,
    tree: bool,
) -> list[str]:
    """Plan rows for a summary; plan, milestone, and task rows for a tree."""
    lines: list[str] = []
    for plan, milestones in services.tree(
        store,
        status=status,
        plan_id=plan_id,
        archived=archived,
        limit=limit,
        repo=repo,
        milestone_id=milestone_id,
    ):
        lines.append(_porcelain_row(store, plan))
        if not tree:
            continue
        for milestone, tasks in milestones:
            lines.append(_porcelain_row(store, milestone))
            lines.extend(_porcelain_row(store, task) for task in tasks)
    return lines


def _note_dict_rows(items: list[dict]) -> list[str]:
    """Note rows from show/brief payload dicts."""
    return [
        porcelain.note_row(
            note["id"],
            note.get("actor"),
            note.get("text"),
            note.get("parent_kind", "note"),
            note.get("parent_id", "-"),
            note.get("ts", 0),
        )
        for note in items
    ]


def _gate_row(gate: dict | None) -> list[str]:
    """Porcelain gate row when a task has linked PRs."""
    if not gate:
        return []
    return [
        porcelain.row(
            "gate",
            gate.get("state"),
            gate.get("checks"),
            f"{gate.get('prs', 0)} PRs",
            "-",
            "-",
        )
    ]


def _issue_dict_rows(items: list[dict]) -> list[str]:
    """Porcelain issue-source rows."""
    return [
        porcelain.row(
            "issue",
            item.get("number") or item.get("external_id"),
            item.get("state"),
            item.get("title"),
            f"{item.get('provider')}:{item.get('external_id')}",
            item.get("url") or "-",
        )
        for item in items
    ]


def _comment_dict_rows(items: list[dict]) -> list[str]:
    """Comment rows from show/brief payload dicts."""
    return [
        porcelain.comment_row(
            item["id"],
            item.get("actor"),
            item.get("text"),
            item.get("parent_kind", "comment"),
            item.get("parent_id", "-"),
            item.get("ts", 0),
            bool(item.get("resolved")),
        )
        for item in items
    ]


def _claim_line(store: Store, task_id: int, title: str) -> str | None:
    """Claim row for a task, or None when it has no lease."""
    claim = store.get_claim(task_id)
    if claim is None:
        return None
    return porcelain.claim_row(task_id, claim.actor, title, claim.expires_at)


def _porcelain_show_lines(store: Store, kind: str, full: dict) -> list[str]:
    """Plain definition rows plus criteria and children; no repo or commit noise."""
    lines: list[str] = []
    if kind == "plan":
        plan = full["plan"]
        lines.append(
            porcelain.plan_row(
                plan["id"], plan["status"], plan["name"], _progress(store, plan_id=plan["id"])
            )
        )
        lines.append(porcelain.text_row("why", plan.get("goal")))
        lines.append(porcelain.text_row("what", plan.get("description")))
        lines.extend(_criterion_dict_rows(full.get("criteria", [])))
        lines.extend(_note_dict_rows(full.get("notes", [])))
        lines.extend(_comment_dict_rows(full.get("comments", [])))
        lines.extend(_issue_dict_rows(full.get("issues", [])))
        for entry in full.get("milestones", []):
            milestone = entry["milestone"]
            lines.append(
                porcelain.milestone_row(
                    milestone["id"],
                    milestone["status"],
                    milestone["title"],
                    milestone["plan_id"],
                    _progress(store, milestone_id=milestone["id"]),
                )
            )
            lines.extend(_criterion_dict_rows(entry.get("criteria", [])))
            for task in entry.get("tasks", []):
                lines.append(
                    porcelain.task_row(
                        task["id"],
                        task["status"],
                        task["title"],
                        task["milestone_id"],
                        "blocked" if task.get("blocked") else "-",
                    )
                )
                claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
                if claim_line is not None:
                    lines.append(claim_line)
                lines.extend(_gate_row(task.get("gate")))
                lines.extend(_note_dict_rows(task.get("notes", [])))
                lines.extend(_comment_dict_rows(task.get("comments", [])))
                lines.extend(_issue_dict_rows(task.get("issues", [])))
        return lines
    if kind == "milestone":
        milestone = full["milestone"]
        lines.append(
            porcelain.milestone_row(
                milestone["id"],
                milestone["status"],
                milestone["title"],
                milestone["plan_id"],
                _progress(store, milestone_id=milestone["id"]),
            )
        )
        lines.append(porcelain.text_row("desc", milestone.get("description")))
        lines.extend(_criterion_dict_rows(full.get("criteria", [])))
        lines.extend(_note_dict_rows(full.get("notes", [])))
        lines.extend(_comment_dict_rows(full.get("comments", [])))
        lines.extend(_issue_dict_rows(full.get("issues", [])))
        for entry in full.get("tasks", []):
            task = entry["task"]
            lines.append(
                porcelain.task_row(
                    task["id"],
                    task["status"],
                    task["title"],
                    task["milestone_id"],
                    "blocked" if task.get("blocked") else "-",
                )
            )
            claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
            if claim_line is not None:
                lines.append(claim_line)
            lines.extend(_gate_row(task.get("gate")))
            lines.extend(_note_dict_rows(task.get("notes", [])))
            lines.extend(_comment_dict_rows(task.get("comments", [])))
            lines.extend(_issue_dict_rows(task.get("issues", [])))
        return lines
    task = full["task"]
    lines.append(
        porcelain.task_row(
            task["id"],
            task["status"],
            task["title"],
            task["milestone_id"],
            "blocked" if task.get("blocked") else "-",
        )
    )
    claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
    if claim_line is not None:
        lines.append(claim_line)
    lines.extend(_gate_row(task.get("gate")))
    lines.append(porcelain.text_row("desc", task.get("description")))
    lines.extend(_criterion_dict_rows(full.get("criteria", [])))
    lines.extend(_note_dict_rows(task.get("notes", [])))
    lines.extend(_comment_dict_rows(task.get("comments", [])))
    lines.extend(_issue_dict_rows(task.get("issues", [])))
    return lines


def _criterion_dict_rows(items: list[dict]) -> list[str]:
    """Criterion rows from `show` or `brief` payload dicts."""
    return [
        porcelain.row(
            "criterion",
            item["id"],
            "done" if item.get("done") else "open",
            item.get("text"),
            f"{item.get('parent_kind', item.get('kind'))}:{item.get('parent_id', item.get('id'))}",
            "-",
        )
        for item in items
    ]


def _commit_row(link: dict, parent: str) -> str:
    """One commit record; the full SHA stays the id."""
    return porcelain.row(
        "commit",
        link.get("sha"),
        "stale" if link.get("stale") else "linked",
        link.get("subject"),
        parent,
        link.get("repo_root") or "-",
    )


def _repo_row(row: dict, parent: str, status: str) -> str:
    """One repo link; title carries the remote and extra the branch."""
    return porcelain.row(
        "repo",
        row.get("repo_path"),
        status,
        row.get("repo_remote") or "-",
        parent,
        row.get("branch") or "-",
    )


def _feed_row(event: dict) -> str:
    """One feed event: id, actor, detail, event kind/action, and timestamp."""
    return porcelain.row(
        "feed",
        event.get("id"),
        event.get("actor"),
        event.get("detail"),
        f"{event.get('kind')}/{event.get('action')}",
        int(float(event.get("ts") or 0)),
    )


def _info_rows(payload: dict) -> list[str]:
    """`info` as key/value rows, including each count."""
    rows = [
        porcelain.row("info", "db", "-", payload.get("db"), "-", "-"),
        porcelain.row("info", "repo", "-", payload.get("repo"), "-", "-"),
        porcelain.row("info", "scope", "-", payload.get("scope"), "-", "-"),
        porcelain.row(
            "info",
            "plan_files",
            "-",
            ",".join(str(name) for name in payload.get("plan_files", [])),
            "-",
            "-",
        ),
    ]
    for key, value in (payload.get("counts") or {}).items():
        rows.append(porcelain.row("info", key, "-", value, "-", "-"))
    return rows


def _audit_rows(report: audit.Report) -> list[str]:
    """Audit metrics plus every open gap."""
    window = (
        "all history"
        if not report.since
        else time.strftime("%Y-%m-%d %H:%M", time.localtime(report.since))
    )
    rows = [
        porcelain.row("metric", "plans", "-", ",".join(f"P{plan}" for plan in report.plans)),
        porcelain.row("metric", "since", "-", window),
        porcelain.row("metric", "repos", "-", len(report.repos)),
        porcelain.row("metric", "commits_total", "-", report.commits_total),
        porcelain.row("metric", "commits_linked", "-", report.commits_linked),
        porcelain.row("metric", "coverage", "-", round(report.coverage, 4)),
        porcelain.row("metric", "median_lag_commits", "-", report.median_lag_commits),
        porcelain.row("metric", "median_lag_minutes", "-", report.median_lag_minutes),
        porcelain.row("metric", "unresolved_lag", "-", report.unresolved),
        porcelain.row("metric", "gaps", "-", len(report.gaps)),
        porcelain.row("metric", "criteria_total", "-", report.criteria_total),
        porcelain.row("metric", "criteria_linked", "-", report.criteria_linked),
        porcelain.row("metric", "trace_coverage", "-", round(report.trace_coverage, 4)),
        porcelain.row("metric", "trace_gaps", "-", len(report.trace_gaps)),
    ]
    rows.extend(porcelain.row("gap", f"{gap.kind}:{gap.id}", "-", gap.text) for gap in report.gaps)
    rows.extend(
        porcelain.row("gap", f"{gap.kind}:{gap.id}", "-", gap.text) for gap in report.trace_gaps
    )
    return rows


def _brief_rows(store: Store, payload: dict) -> list[str]:
    """Brief as plan, doing, next, criterion, and unlinked commit rows."""
    rows = [porcelain.row("metric", "active", "-", payload.get("active", 0))]
    for entry in payload.get("plans", []):
        plan = store.get_plan(int(entry["id"]))
        if plan is not None:
            rows.append(_porcelain_row(store, plan))
        rows.extend(_note_dict_rows(entry.get("notes", [])))
        rows.extend(_comment_dict_rows(entry.get("comments", [])))
        for task in entry.get("doing", []):
            model = store.get_task(int(task["id"]))
            if model is not None:
                rows.append(_porcelain_row(store, model))
                claim_line = _claim_line(store, int(task["id"]), str(task["title"]))
                if claim_line is not None:
                    rows.append(claim_line)
                rows.extend(_gate_row(task.get("gate")))
                rows.extend(_note_dict_rows(task.get("notes", [])))
                rows.extend(_comment_dict_rows(task.get("comments", [])))
        next_task = entry.get("next")
        if next_task:
            parent = "-"
            model = store.get_task(int(next_task["id"]))
            if model is not None:
                parent = f"milestone:{model.milestone_id}"
            rows.append(
                porcelain.row("next", next_task["id"], "-", next_task["title"], parent, "-")
            )
        rows.extend(_criterion_dict_rows(entry.get("criteria", [])))
        for commit in entry.get("unlinked", []):
            rows.append(
                porcelain.row(
                    "commit",
                    commit.get("sha"),
                    "unlinked",
                    commit.get("subject"),
                    f"plan:{entry['id']}",
                    int(float(commit.get("timestamp") or 0)),
                )
            )
    return rows


def _git_status_rows(entries: list[dict], parent: str) -> list[str]:
    """One row per checkout with branch, dirty state, and tracking facts."""
    rows: list[str] = []
    for entry in entries:
        path = entry.get("repo_path")
        if entry.get("error"):
            rows.append(
                porcelain.row(
                    "status", path, "error", entry["error"], parent, entry.get("repo_remote")
                )
            )
            continue
        branch = entry.get("branch") or ("detached" if entry.get("detached") else "unknown")
        head = str(entry.get("head") or "")[:12]
        extra = (
            f"head={head or '-'} ahead={entry.get('ahead', 0)} behind={entry.get('behind', 0)} "
            f"upstream={entry.get('upstream') or '-'} subject={entry.get('subject') or '-'}"
        )
        rows.append(
            porcelain.row(
                "status",
                path,
                "dirty" if entry.get("dirty") else "clean",
                branch,
                parent,
                extra,
            )
        )
    return rows


def _pr_row(link: dict, parent: str) -> str:
    """One pull request; title is the PR title and extra is the URL."""
    return porcelain.row(
        "pr",
        link.get("number"),
        link.get("state") or "unknown",
        link.get("title") or "-",
        parent,
        link.get("url") or "-",
    )


def _pr_status_rows(entries: list[dict], parent: str) -> list[str]:
    """One row per checkout with provider, auth source, and cache state."""
    rows: list[str] = []
    for entry in entries:
        path = entry.get("repo_path")
        summary = (
            f"{entry.get('provider', 'github')} auth={entry.get('auth_source') or 'none'} "
            f"cache={entry.get('cache') or 'none'} remote={entry.get('repo_remote') or '-'}"
        )
        if entry.get("error"):
            rows.append(porcelain.row("pr-status", path, "error", entry["error"], parent, summary))
        else:
            rows.append(
                porcelain.row("pr-status", path, "ready", entry.get("slug") or "-", parent, summary)
            )
    return rows


def _scan_row(match: dict) -> str:
    """One git scan match: SHA, action, subject, and the matched row ref."""
    return porcelain.row(
        "scan", match.get("sha"), match.get("action"), match.get("subject"), match.get("ref"), "-"
    )


def _cmd_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    archived, status = _list_filters(args)
    limit = _list_limit(args)
    repo_filter = getattr(args, "repo", None)
    milestone_filter = getattr(args, "milestone", None)
    if args.json:
        return _emit(
            args,
            _list_payload(
                store,
                status,
                archived,
                limit,
                repo_filter,
                milestone_filter,
                args.plan,
            ),
        )
    if porcelain.enabled(args):
        for line in _porcelain_list_lines(
            store,
            status,
            args.plan,
            archived,
            limit,
            repo_filter,
            milestone_filter,
            bool(getattr(args, "tree", False)) or milestone_filter is not None,
        ):
            print(line)
        return 0
    lines = _list_lines(store, args, status, archived, limit, repo_filter, milestone_filter)
    print("\n".join(lines) if lines else EMPTY_NO_PLANS)
    return 0


def _cmd_help(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.json:
        return _emit(args, {"help": HELP_TEXT})
    print(HELP_TEXT)
    return 0


def _cmd_add_plan(store: Store, args: argparse.Namespace, actor: str) -> int:
    title = _resolve_title(args)
    if not title.strip():
        print("error: plan add needs --title", file=sys.stderr)
        return 2
    desc = args.desc if args.desc is not None else (args.what or "")
    goal = args.goal if args.goal is not None else (args.why or "")
    p = services.create_plan(
        store,
        title,
        desc,
        goal=goal,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, p), {"plan": _ser(vars(p))})


def _cmd_add_milestone(store: Store, args: argparse.Namespace, actor: str) -> int:
    s = services.create_milestone(
        store,
        args.plan,
        args.title,
        args.desc,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, s), {"milestone": _ser(vars(s))})


def _cmd_add_task(store: Store, args: argparse.Namespace, actor: str) -> int:
    t = services.create_task(
        store,
        args.milestone,
        args.title,
        description=args.desc,
        actor=actor,
    )
    return _emit_record(args, _porcelain_row(store, t), {"task": _ser(vars(t))})


def _cmd_update(store: Store, args: argparse.Namespace, actor: str) -> int:
    title_patch = _resolve_title(args) or None
    desc_patch: str | None = args.desc if args.desc is not None else args.what
    updated: Plan | Milestone | Task | None = None
    if args.kind == "plan":
        goal = args.goal if args.goal is not None else args.why
        updated = store.update_plan(
            args.id,
            name=title_patch,
            description=desc_patch,
            goal=goal,
            actor=actor,
        )
    elif args.kind == "milestone":
        updated = store.update_milestone(
            args.id,
            title=title_patch,
            description=desc_patch,
            actor=actor,
        )
    else:
        updated = store.update_task(
            args.id,
            title=title_patch,
            description=desc_patch,
            actor=actor,
        )
    if updated is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    return _emit_record(args, _porcelain_row(store, updated), {"updated": _ser(vars(updated))})


def _cmd_show(store: Store, args: argparse.Namespace, actor: str) -> int:
    full = store.get_full(args.kind, args.id)
    if full is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(args, full)
    if porcelain.enabled(args):
        for line in _porcelain_show_lines(store, args.kind, full):
            print(line)
        return 0
    print(render_full(args.kind, full, files=bool(getattr(args, "files", False))))
    return 0


def _cmd_status(store: Store, args: argparse.Namespace, actor: str) -> int:
    left = store.open_criteria(args.kind, args.id)
    if args.to == "done" and left:
        print(
            f"warning: {len(left)} open acceptance criteria "
            f"({', '.join(c.text[:40] for c in left[:3])}); closing anyway",
            file=sys.stderr,
        )
    ok = services.set_status(store, args.kind, args.id, Status(args.to), actor=actor)
    if not ok:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.to == "done":
        reason = services.auto_capture_head(store, args.kind, args.id, actor=actor)
        if reason:
            print(
                f"warning: {args.kind} #{args.id} done, but HEAD was not linked: {reason}. "
                f"Commit, then run `lpui link --kind {args.kind} --id {args.id}`.",
                file=sys.stderr,
            )
    payload = {"ok": True, "kind": args.kind, "id": args.id, "to": args.to}
    if porcelain.enabled(args):
        moved = store.get_parent(args.kind, args.id)
        if moved is not None:
            return _emit_record(args, _porcelain_row(store, moved), payload)
    return _emit(args, payload)


def _cmd_reconcile(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _emit(args, {"reconciled": services.reconcile(store, actor=actor)})


def _cmd_delete(store: Store, args: argparse.Namespace, actor: str) -> int:
    before = store.get_parent(args.kind, args.id)
    title = "-"
    parent = "-"
    if isinstance(before, Plan):
        title = before.name
    elif isinstance(before, Milestone):
        title = before.title
        parent = f"plan:{before.plan_id}"
    elif isinstance(before, Task):
        title = before.title
        parent = f"milestone:{before.milestone_id}"
    ok = store.delete(args.kind, args.id, actor=actor)
    if not ok:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    line = porcelain.row(args.kind, args.id, "deleted", title, parent, "-")
    return _emit_record(args, line, {"ok": True, "deleted": f"{args.kind} #{args.id}"})


def _cmd_add_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    c = store.add_criteria(args.kind, args.id, args.text, actor=actor)
    return _emit_record(args, _criterion_row(c), {"criteria": vars(c)})


def _cmd_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    found = store.get_parent(args.kind, args.id)
    if found is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    items = store.list_criteria(args.kind, args.id)
    if porcelain.enabled(args):
        for item in items:
            print(_criterion_row(item))
        return 0
    return _emit(args, [vars(c) for c in items])


def _check_uncheck(store: Store, args: argparse.Namespace, actor: str, done: bool) -> int:
    crit = store.set_criteria(args.id, done, actor=actor)
    if crit is None:
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    return _emit_record(args, _criterion_row(crit), {"criteria": vars(crit)})


def _cmd_check(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, True)


def _cmd_uncheck(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, False)


def _cmd_delete_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    if not store.delete_criteria(args.id, actor=actor):
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    line = porcelain.row("criterion", args.id, "deleted", "-", "-", "-")
    return _emit_record(args, line, {"ok": True, "deleted": f"criteria #{args.id}"})


def _cmd_issue_import(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.as_kind == "task":
        if not args.milestone or store.get_milestone(args.milestone) is None:
            print(msg_error(ValueError("--as task needs a valid --milestone")), file=sys.stderr)
            return 2
    try:
        if args.provider == "github":
            if not args.repo or "/" not in args.repo:
                print("error: github import needs --repo OWNER/REPO", file=sys.stderr)
                return 2
            owner, repo = args.repo.split("/", 1)
            client = GitHubClient(auth=resolve_auth(), store=store)
            fetched = client.issues(RepoRef("github", "github.com", owner, repo))
            parsed = issues_mod.parse_github(fetched.data)
        else:
            if not args.file:
                print("error: linear import needs --file PATH", file=sys.stderr)
                return 2
            parsed = issues_mod.parse_linear(json.loads(Path(args.file).read_text()))
    except (OSError, ValueError, GitHubError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    report = issues_mod.import_issues(
        store,
        parsed,
        actor=actor,
        as_kind=args.as_kind,
        milestone=args.milestone,
        dry_run=bool(args.dry_run),
    )
    if args.json:
        return _emit(args, report)
    print(
        f"{'dry-run: ' if report['dry_run'] else ''}"
        f"{len(report['created'])} created · {len(report['updated'])} updated"
    )
    for item in report["created"]:
        print(f"  {item['provider']} {item['id']} -> {item['row_kind']} {item['row_id']}")
    return 0


def _criterion_link(store: Store, args: argparse.Namespace, actor: str, relate: bool) -> int:
    criterion = store.get_criterion(args.id)
    if criterion is None:
        print(msg_not_found("criterion", args.id), file=sys.stderr)
        return 1
    task = store.get_task(args.task)
    if task is None:
        print(msg_not_found("task", args.task), file=sys.stderr)
        return 1
    try:
        if relate:
            store.relate_criterion(args.id, args.task, actor=actor)
        else:
            if not store.unrelate_criterion(args.id, args.task, actor=actor):
                print(
                    msg_error(
                        ValueError(f"criterion #{args.id} is not linked to task #{args.task}")
                    ),
                    file=sys.stderr,
                )
                return 1
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    payload = {
        "link": {
            "criterion_id": args.id,
            "task_id": args.task,
            "task": task.title,
            "linked": relate,
        }
    }
    if args.json:
        return _emit(args, payload)
    if porcelain.enabled(args):
        print(
            porcelain.link_row(args.id, "linked" if relate else "unlinked", args.task, task.title)
        )
    else:
        verb = "linked" if relate else "unlinked"
        print(f"{verb} criterion #{args.id} {'to' if relate else 'from'} T{args.task} {task.title}")
    return 0


def _cmd_criterion_relate(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _criterion_link(store, args, actor, True)


def _cmd_criterion_unrelate(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _criterion_link(store, args, actor, False)


def _cmd_git_scan(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.id is not None and not args.kind:
        print(msg_error(ValueError("--id needs --kind")), file=sys.stderr)
        return 2
    matches = services.scan_commits(
        store,
        repo_path=str(args.repo) if args.repo else ".",
        since=str(args.since) if args.since else "",
        limit=args.limit,
        dry_run=bool(args.dry_run),
        kind=str(args.kind) if args.kind else "",
        obj_id=args.id or 0,
        actor=actor,
    )
    text = "\n".join(
        f"{match['sha'][:12]} {match['subject']} -> {match['ref']} ({match['action']})"
        for match in matches
    )
    return _emit_read(
        args,
        matches,
        [_scan_row(match) for match in matches],
        text,
        "(no lazyplan references found)",
    )


def _cmd_pr_auth(store: Store, args: argparse.Namespace, actor: str) -> int:
    auth = resolve_auth()
    payload = {
        "provider": "github",
        "source": auth.source,
        "available": auth.available,
    }
    if args.json:
        return _emit(args, payload)
    if auth.available:
        print(f"github auth: {auth.source}")
    else:
        print("github auth: none (set GITHUB_TOKEN or run `gh auth login`)")
    return 0


def _cmd_pr_status(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.kind or args.id:
        if not (args.kind and args.id):
            print(msg_error(ValueError("--kind and --id go together")), file=sys.stderr)
            return 2
        if store.get_parent(args.kind, args.id) is None:
            print(msg_not_found(args.kind, args.id), file=sys.stderr)
            return 1
    auth = resolve_auth()
    entries = services.forge_statuses(
        store,
        kind=str(args.kind) if args.kind else "",
        obj_id=args.id or 0,
        repo_path=str(args.repo) if args.repo else "",
        auth=auth,
    )
    parent = f"{args.kind}:{args.id}" if args.kind and args.id else "-"
    return _emit_read(
        args,
        entries,
        _pr_status_rows(entries, parent),
        render_forge_status(entries) if entries else "",
        "(no linked repos)",
    )


def _cmd_pr_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    links = store.list_forge_links(args.kind, args.id)
    parent = f"{args.kind}:{args.id}"
    return _emit_read(
        args,
        [vars(link) for link in links],
        [_pr_row(vars(link), parent) for link in links],
        render_forge_links([vars(link) for link in links]) if links else "",
        "(no pull requests linked)",
    )


def _cmd_pr_show(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    links = [
        link for link in store.list_forge_links(args.kind, args.id) if link.number == args.number
    ]
    if not links:
        print(msg_not_found("pull request", args.number), file=sys.stderr)
        return 1
    link = vars(links[0])
    return _emit_read(
        args,
        link,
        [_pr_row(link, f"{args.kind}:{args.id}")],
        render_forge_links([link]),
    )


def _cmd_pr_link(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    parsed = parse_pull_url(str(args.url))
    if parsed is None:
        print(
            msg_error(ValueError(f"not a GitHub pull request URL: {args.url!r}")), file=sys.stderr
        )
        return 2
    ref, number = parsed
    state = str(args.state) if args.state else ""
    title = str(args.title) if args.title else f"PR #{number}"
    link = store.link_forge(
        args.kind,
        args.id,
        number,
        provider="github",
        kind="pull",
        url=str(args.url),
        title=title,
        state=state,
        payload=f'{{"repository": "{ref.owner}/{ref.repo}"}}',
        actor=actor,
    )
    line = porcelain.row("pr", link.number, "linked", link.url, f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"link": vars(link)})


def _cmd_pr_unlink(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    ok = store.unlink_forge(args.kind, args.id, args.number, actor=actor)
    if not ok:
        print(msg_not_found("pull request", args.number), file=sys.stderr)
        return 1
    line = porcelain.row("pr", args.number, "unlinked", "-", f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"ok": True, "unlinked": f"PR #{args.number}"})


def _cmd_pr_refresh(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    stats = services.refresh_forge(store, args.kind, args.id, actor=actor)
    for error in stats["errors"]:
        ref = str(error.get("sha") or error.get("branch") or error.get("merge_commit") or "refresh")
        if error.get("sha"):
            ref = ref[:12]
        print(f"warning: {ref}: {error.get('error', '')}", file=sys.stderr)
    if args.json:
        return _emit(args, stats)
    print(
        f"linked {stats['linked']} PRs from {stats['commits']} commits and "
        f"{stats['branches']} branches ({stats['merges']} merges, "
        f"{stats['stale']} cached, {stats['skipped']} skipped)"
    )
    return 0 if stats["linked"] or not stats["errors"] else 1


def _cmd_link(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    target = str(args.repo) if getattr(args, "repo", None) else "."
    backend, root = detect_backend(target)
    if backend is None or root is None:
        print(msg_no_vcs(), file=sys.stderr)
        return 2
    sha = str(args.sha) if getattr(args, "sha", None) else backend.head(root)
    if sha is None:
        print(msg_no_head(), file=sys.stderr)
        return 2
    info = backend.show(root, sha)
    if info is None:
        print(msg_error(ValueError(f"unknown commit {sha!r}")), file=sys.stderr)
        return 2
    link = store.link_commit(
        args.kind,
        args.id,
        info.sha,
        subject=info.subject,
        author=info.author,
        timestamp=info.timestamp,
        repo_root=info.repo_root,
        files=info.files,
        actor=actor,
    )
    line = porcelain.row("commit", link.sha, "linked", link.subject, f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"link": vars(link)})


def _cmd_unlink(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    backend, _root = detect_backend(".")
    if backend is None:
        print(msg_no_vcs(), file=sys.stderr)
        return 2
    ok = store.unlink_commit(args.kind, args.id, str(args.sha), actor=actor)
    if not ok:
        print(msg_error(ValueError(f"no such link {args.sha!r}")), file=sys.stderr)
        return 1
    line = porcelain.row("commit", args.sha, "unlinked", "-", f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"ok": True, "unlinked": str(args.sha)})


def _cmd_commits(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if getattr(args, "refresh", False):
        services.refresh_links(store, args.kind, args.id, actor=actor)
    links = store.effective_links(args.kind, args.id)
    parent = f"{args.kind}:{args.id}"
    text = (
        render_commits([vars(c) for c in links], files=bool(getattr(args, "files", False)))
        if links
        else ""
    )
    return _emit_read(
        args,
        [vars(c) for c in links],
        [_commit_row(vars(link), parent) for link in links],
        text,
        EMPTY_COMMITS,
    )


def _cmd_task_start(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_task(args.id) is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    result = services.start_task(
        store,
        args.id,
        repo_path=str(args.repo) if args.repo else "",
        branch=str(args.branch) if args.branch else "",
        actor=actor,
    )
    if args.json:
        return _emit(args, result)
    if porcelain.enabled(args):
        task = store.get_task(args.id)
        if task is not None:
            return _emit_record(args, _porcelain_row(store, task), result)
    print(f"started T{result['task']} on {result['branch']} (base {result['base_sha'][:12]})")
    return 0


def _cmd_task_block(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_task(args.id) is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    try:
        task = services.block_task(store, args.id, args.reason, actor=actor)
    except KeyError:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        return _emit(args, {"task": _ser(vars(task))})
    if porcelain.enabled(args):
        print(_porcelain_row(store, task))
    else:
        print(f"blocked T{task.id}: {task.blocked_reason}")
    return 0


def _cmd_task_unblock(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_task(args.id) is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    try:
        task = services.unblock_task(store, args.id, actor=actor)
    except (KeyError, ValueError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        return _emit(args, {"task": _ser(vars(task))})
    if porcelain.enabled(args):
        print(_porcelain_row(store, task))
    else:
        print(f"unblocked T{task.id}")
    return 0


def _cmd_task_finish(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_task(args.id) is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    try:
        result = services.finish_task(
            store,
            args.id,
            repo_path=str(args.repo) if args.repo else "",
            actor=actor,
            require_pr=bool(getattr(args, "require_pr", False)),
            require_checks=bool(getattr(args, "require_checks", False)),
            override=str(getattr(args, "override", "") or ""),
        )
    except services.GateError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    if args.json:
        return _emit(args, result)
    if porcelain.enabled(args):
        task = store.get_task(args.id)
        if task is not None:
            return _emit_record(args, _porcelain_row(store, task), result)
    print(
        f"linked {result['linked']} commit(s) on {result['branch']} from {result['base_sha'][:12]}"
    )
    if result["done"]:
        print(f"T{result['task']} done")
    else:
        print(f"T{result['task']} left doing: working tree is dirty")
    return 0


def _cmd_git_status(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.kind or args.id:
        if not (args.kind and args.id):
            print(msg_error(ValueError("--kind and --id go together")), file=sys.stderr)
            return 2
        if store.get_parent(args.kind, args.id) is None:
            print(msg_not_found(args.kind, args.id), file=sys.stderr)
            return 1
    entries = services.repo_statuses(
        store,
        kind=str(args.kind) if args.kind else "",
        obj_id=args.id or 0,
        repo_path=str(args.repo) if args.repo else "",
    )
    parent = f"{args.kind}:{args.id}" if args.kind and args.id else "-"
    return _emit_read(
        args,
        entries,
        _git_status_rows(entries, parent),
        render_git_status(entries) if entries else "",
        "(no linked repos)",
    )


def _repo_remote_default(repo_path: str) -> str:
    """Best-effort remote URL for a checkout path (origin fetch, else first)."""
    backend, root = detect_backend(repo_path)
    if backend is None or root is None:
        return ""
    return origin_url(backend, root)


def _cmd_link_repo(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    remote = args.remote
    if remote is None:
        remote = _repo_remote_default(str(args.repo))
    try:
        row = store.add_repo_link(args.kind, args.id, str(args.repo), remote or "", actor=actor)
    except (ValueError, KeyError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    line = porcelain.row(
        "repo",
        row["repo_path"],
        "linked",
        row.get("repo_remote") or "-",
        f"{args.kind}:{args.id}",
        "-",
    )
    return _emit_record(args, line, {"repo": row})


def _cmd_unlink_repo(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    ok = store.remove_repo_link(args.kind, args.id, str(args.repo), args.remote, actor=actor)
    if not ok:
        print(msg_error(ValueError(f"no such repo link {args.repo!r}")), file=sys.stderr)
        return 1
    line = porcelain.row("repo", str(args.repo), "unlinked", "-", f"{args.kind}:{args.id}", "-")
    return _emit_record(args, line, {"ok": True, "unlinked": str(args.repo)})


def _cmd_repos(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    rows = (
        store.effective_repos(args.kind, args.id)
        if getattr(args, "effective", False)
        else store.list_repos(args.kind, args.id)
    )
    status = "effective" if getattr(args, "effective", False) else "explicit"
    parent = f"{args.kind}:{args.id}"
    text = "\n".join(
        f"{row['repo_path']}" + (f" ({row['repo_remote']})" if row.get("repo_remote") else "")
        for row in rows
    )
    return _emit_read(
        args,
        rows,
        [_repo_row(row, parent, status) for row in rows],
        text,
        EMPTY_COMMITS,
    )


def _cmd_export(store: Store, args: argparse.Namespace, actor: str) -> int:
    from .render import render_plan_markdown

    plan_id = getattr(args, "plan", None)
    dest = getattr(args, "file", None)
    if plan_id is not None:
        entry = services.export_plan(store, plan_id)
        if entry is None:
            print(msg_not_found("plan", plan_id), file=sys.stderr)
            return 1
        if args.format == "json":
            payload: object = {"lazyplan": 1, "plans": [entry]}
            text = json.dumps(payload, indent=2, default=str)
        else:
            text = render_plan_markdown(entry)
    else:
        data = services.export_all(store)
        if args.format == "json":
            return _emit(args, data)
        text = render_markdown(data)
    if dest:
        Path(dest).write_text(text + ("" if text.endswith("\n") else "\n"))
        return _emit(args, {"exported": dest})
    print(text)
    return 0


def _cmd_import(store: Store, args: argparse.Namespace, actor: str) -> int:
    import json as _json

    with open(args.file) as fh:
        data = _json.load(fh)
    try:
        counts = services.import_all(store, data, actor=actor)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit(args, {"imported": counts})


def _print_feed_events(
    events: list[dict], terse: bool, *, reverse: bool = False, flush: bool = False
) -> None:
    """Print feed events in one format; callers choose order and buffering."""
    items = reversed(events) if reverse else events
    for event in items:
        if terse:
            print(_feed_row(event), flush=flush)
        else:
            print(
                f"#{event['id']} [{event['actor']}] "
                f"{event['kind']}/{event['action']}: {event['detail']}",
                flush=flush,
            )


def _cmd_feed(store: Store, args: argparse.Namespace, actor: str) -> int:
    seen = -1
    terse = porcelain.enabled(args)
    while True:
        events = store.feed(args.limit)
        if not args.follow:
            if args.json:
                print(json.dumps(events, indent=2, default=str))
            else:
                if not events and not terse:
                    print(EMPTY_FEED)
                _print_feed_events(events, terse, reverse=True)
            return 0
        fresh = [event for event in events if event["id"] > seen]
        if args.json:
            for event in reversed(fresh):
                print(json.dumps(event, default=str))
        else:
            _print_feed_events(fresh, terse, reverse=True, flush=True)
        if fresh:
            seen = max(event["id"] for event in fresh)
        time.sleep(args.interval)


def _cmd_completion(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    parser = build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    cmds = list(subs.choices)
    if args.shell == "bash":
        print(f'complete -W "{" ".join(cmds)}" lpui')
        print(f'complete -W "{" ".join(cmds)}" lazyplan')
    else:
        print(f"#compdef lpui lazyplan\n_arguments '1:command:({' '.join(cmds)})'")
    return 0


def _interactive_terminal() -> bool:
    """True only when both ends are a terminal; piped runs get the summary."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _plain_overview(store: Store, args: argparse.Namespace) -> int:
    """Non-TTY fallback: a readable summary instead of full-screen ANSI."""
    if getattr(args, "json", False):
        return _emit(
            args,
            _list_payload(store, None, "hide", None, None, None, None),
        )
    print(
        "lpui: no interactive terminal; showing the plan summary (use `lpui list --tree` for detail)",
        file=sys.stderr,
    )
    lines = summary_lines(
        store,
        None,
        None,
        dot="plain",
        archived="hide",
        limit=services.DEFAULT_PLAN_LIMIT,
    )
    print("\n".join(lines) if lines else EMPTY_NO_PLANS)
    return 0


def _cmd_ui(store: Store, args: argparse.Namespace, actor: str) -> int:
    del actor
    if not _interactive_terminal():
        return _plain_overview(store, args)
    from .tui import run

    return run(db_path=args.db)


def _maybe_notice_update(args: argparse.Namespace) -> None:
    """One stderr notice per process when a newer release exists; never breaks."""
    if args.cmd in (None, "ui", "upgrade"):
        return
    if getattr(args, "json", False) or getattr(args, "version", False):
        return
    try:
        latest = latest_version(timeout=NOTICE_TIMEOUT)
        notice = notice_text(detect(), package_version(), latest)
    except Exception:
        return
    if notice is not None:
        print(notice, file=sys.stderr)


def _cmd_upgrade(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Upgrade this install to the latest release; needs no database."""
    del store, actor
    info = detect()
    installed = package_version()
    try:
        latest = latest_version()
    except UpgradeError as exc:
        # Fail open: a missing network must never break the tool.
        if args.json:
            return _emit(
                args,
                {
                    "method": info.method,
                    "upgradeable": info.upgradeable,
                    "installed": installed,
                    "latest": None,
                    "upgraded": False,
                    "warning": str(exc),
                },
            )
        print(f"warning: {exc}; skipping upgrade check", file=sys.stderr)
        return 0
    payload = {
        "method": info.method,
        "upgradeable": info.upgradeable,
        "installed": installed,
        "latest": latest,
        "upgraded": False,
    }
    if not info.upgradeable and not args.check:
        print(msg_error(UpgradeError(guard_message(info))), file=sys.stderr)
        return 2
    try:
        up_to_date = parse_version(latest) <= parse_version(installed)
    except UpgradeError:
        up_to_date = False
    if args.check or up_to_date:
        if args.json:
            return _emit(args, payload)
        if up_to_date:
            print(f"lpui v{installed} is the latest release ({info.method})")
        else:
            print(f"lpui v{installed} -> v{latest} available ({info.method}); run `lpui upgrade`")
        return 0
    try:
        run_upgrade(info, latest, sys.executable)
    except UpgradeError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 1
    payload["upgraded"] = True
    if not args.json:
        print(f"upgraded lpui v{installed} -> v{latest} ({info.method})")
    _post_upgrade_review(bool(args.json))
    if args.json:
        return _emit(args, payload)
    return 0


def _post_upgrade_review(json_mode: bool = False) -> None:
    """Refresh setup with the just-installed package; never break the upgrade."""
    argv = [sys.executable, "-m", "lazyplan", "setup", "--post-upgrade"]
    if json_mode:
        argv.append("--json")
    try:
        subprocess.run(
            argv,
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL if json_mode else None,
        )
    except (OSError, subprocess.SubprocessError):
        return


_GROUP_CMDS: dict[tuple[str, str], str] = {
    ("plan", "add"): "add-plan",
    ("plan", "edit"): "update",
    ("plan", "show"): "show",
    ("plan", "list"): "list",
    ("plan", "move"): "status",
    ("plan", "delete"): "delete",
    ("milestone", "add"): "add-milestone",
    ("milestone", "edit"): "update",
    ("milestone", "show"): "show",
    ("milestone", "list"): "list",
    ("milestone", "move"): "status",
    ("milestone", "delete"): "delete",
    ("task", "add"): "add-task",
    ("task", "edit"): "update",
    ("task", "show"): "show",
    ("task", "list"): "list",
    ("task", "move"): "status",
    ("task", "delete"): "delete",
    ("task", "start"): "task-start",
    ("task", "finish"): "task-finish",
    ("task", "block"): "task-block",
    ("task", "unblock"): "task-unblock",
    ("criterion", "add"): "add-criteria",
    ("criterion", "list"): "criteria",
    ("criterion", "tick"): "check",
    ("criterion", "untick"): "uncheck",
    ("criterion", "delete"): "delete-criteria",
    ("issue", "import"): "issue-import",
    ("criterion", "relate"): "criterion-relate",
    ("criterion", "unrelate"): "criterion-unrelate",
    ("git", "status"): "git-status",
    ("git", "scan"): "git-scan",
    ("pr", "auth"): "pr-auth",
    ("pr", "status"): "pr-status",
    ("pr", "list"): "pr-list",
    ("pr", "show"): "pr-show",
    ("pr", "link"): "pr-link",
    ("pr", "unlink"): "pr-unlink",
    ("pr", "refresh"): "pr-refresh",
}


_COMMANDS: dict[str, Callable[[Store, argparse.Namespace, str], int]] = {
    "setup": _cmd_setup,
    "doctor": _cmd_doctor,
    "info": _cmd_info,
    "seed": _cmd_seed,
    "list": _cmd_list,
    "help": _cmd_help,
    "trace": _cmd_trace,
    "lint": _cmd_lint,
    "stats": _cmd_stats,
    "comment": _cmd_comment,
    "share": _cmd_share,
    "sync": _cmd_sync,
    "next": _cmd_next,
    "claim": _cmd_claim,
    "claims": _cmd_claims,
    "who": _cmd_claims,
    "note": _cmd_note,
    "add-plan": _cmd_add_plan,
    "add-milestone": _cmd_add_milestone,
    "add-task": _cmd_add_task,
    "update": _cmd_update,
    "show": _cmd_show,
    "status": _cmd_status,
    "reconcile": _cmd_reconcile,
    "delete": _cmd_delete,
    "add-criteria": _cmd_add_criteria,
    "criteria": _cmd_criteria,
    "check": _cmd_check,
    "uncheck": _cmd_uncheck,
    "delete-criteria": _cmd_delete_criteria,
    "issue-import": _cmd_issue_import,
    "criterion-relate": _cmd_criterion_relate,
    "criterion-unrelate": _cmd_criterion_unrelate,
    "link": _cmd_link,
    "unlink": _cmd_unlink,
    "commits": _cmd_commits,
    "git-status": _cmd_git_status,
    "git-scan": _cmd_git_scan,
    "pr-auth": _cmd_pr_auth,
    "pr-status": _cmd_pr_status,
    "pr-list": _cmd_pr_list,
    "pr-show": _cmd_pr_show,
    "pr-link": _cmd_pr_link,
    "pr-unlink": _cmd_pr_unlink,
    "pr-refresh": _cmd_pr_refresh,
    "task-start": _cmd_task_start,
    "task-finish": _cmd_task_finish,
    "task-block": _cmd_task_block,
    "task-unblock": _cmd_task_unblock,
    "link-repo": _cmd_link_repo,
    "unlink-repo": _cmd_unlink_repo,
    "repos": _cmd_repos,
    "export": _cmd_export,
    "import": _cmd_import,
    "upgrade": _cmd_upgrade,
    "feed": _cmd_feed,
    "completion": _cmd_completion,
    "ui": _cmd_ui,
}


def _dispatch_storeless(args: argparse.Namespace, actor: str) -> int | None:
    """Commands that must run before a database is opened; None means keep going."""
    handlers = {
        "upgrade": _cmd_upgrade,
        "setup": _cmd_setup,
        "doctor": _cmd_doctor,
        "audit": _cmd_audit,
        "brief": _cmd_brief,
        "mcp": _cmd_mcp,
        "hook": _cmd_hook,
        "completion": _cmd_completion,
    }
    handler = handlers.get(args.cmd)
    return handler(None, args, actor) if handler is not None else None


def main(argv: list[str] | None = None) -> int:
    """Dispatch one lpui invocation; exit codes are agent-readable."""
    args = build_parser().parse_args(argv)
    noun_group = getattr(args, "noun_group", None)
    if noun_group:
        action = getattr(args, "action", None)
        canonical = _GROUP_CMDS.get((noun_group, action or ""))
        if canonical is None:
            print(f"error: unknown {noun_group} action {action!r}", file=sys.stderr)
            return 2
        args.cmd = canonical
        if noun_group in ("plan", "milestone", "task") and canonical in (
            "update",
            "show",
            "status",
            "delete",
        ):
            args.kind = noun_group
        if noun_group in ("milestone", "task") and canonical == "list":
            args.tree = True
    if getattr(args, "version", False):
        # Before Store(): printing the version must not create a DB.
        print(package_version())
        return 0
    actor = getattr(args, "actor", "human")
    _maybe_notice_update(args)
    if args.cmd is None:
        # Bare `lpui` (or global flags only) opens the standard TUI.
        args.cmd = "ui"
    try:
        setup.ensure(args.cmd, args, Path.cwd(), version=package_version())
    except (OSError, RuntimeError, ValueError) as exc:
        # Setup must never break an agent call; the database still opens.
        print(f"warning: setup skipped: {exc}", file=sys.stderr)
    early = _dispatch_storeless(args, actor)
    if early is not None:
        return early
    # `watch` is `feed --follow`
    if args.cmd == "watch":
        args.cmd = "feed"
        args.follow = True
        args.interval = 1.0
        args.json = getattr(args, "json", False)
    try:
        store = Store(args.db)
    except RuntimeError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    try:
        handler = _COMMANDS.get(args.cmd)
        if handler is None:
            raise AssertionError(args.cmd)
        return handler(store, args, actor)
    except (ValueError, KeyError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
