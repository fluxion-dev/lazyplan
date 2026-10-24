"""`lpui` companion CLI (`lazyplan` is the same binary). Human + agent ingress:
every mutation writes SQLite; the running TUI auto-refreshes. Stdlib only
(no Textual import here)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from . import init_layout, services
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
from .forge import parse_pull_url, resolve_auth
from .models import Milestone, Plan, Status, Task
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
from .repo import (
    find_repo_root,
    repo_label,
    stale_plan_dirs,
)
from .seed import seed as seed_demo
from .skills import (
    SkillPlan,
    append_gitignore,
    apply_skill_plan,
    plan_init,
    prompt_confirm,
)
from .store import Store, _ser
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


def _tty_dot(args: argparse.Namespace) -> str:
    """ANSI dots on a tty; plain otherwise (pipes and --json stay clean)."""
    if getattr(args, "json", False):
        return "plain"
    return "ansi" if sys.stdout.isatty() else "plain"


def _resolve_title(args: argparse.Namespace) -> str:
    """--title wins, --name is the legacy alias."""
    if getattr(args, "title", None):
        return str(args.title)
    if getattr(args, "name", None):
        return str(args.name)
    return ""


def _warn_stale_plan_dir(root: Path | None) -> None:
    """Warn about pre-move plan dirs: ignored, never migrated."""
    if root is None:
        return
    for stale in stale_plan_dirs(root):
        print(
            f"note: {stale}/ is from an older version and is ignored; "
            "carry data over with `lpui export --format json` + `lpui import --file`.",
            file=sys.stderr,
        )


def _print_layout(layout: init_layout.InitLayout, repairs: init_layout.RepairPlan) -> None:
    """Human preflight on stderr; stdout stays JSON."""
    print("lpui init will use:", file=sys.stderr)
    print(f"  database:  {layout.db}", file=sys.stderr)
    print(f"  templates: {layout.templates_dir}", file=sys.stderr)
    if layout.config:
        print(f"  config:    {layout.config}", file=sys.stderr)
    for path in layout.skill_plan.skill_files:
        print(f"  skill:     {path}", file=sys.stderr)
    if layout.agents_md:
        print(f"  agents-md: {layout.agents_md}", file=sys.stderr)
    for entry in layout.gitignore_entries:
        print(f"  gitignore: {entry}", file=sys.stderr)
    for note in init_layout.notes(layout):
        print(f"  note:      {note}", file=sys.stderr)
    if repairs.stop:
        print(f"  stop:      {repairs.stop}", file=sys.stderr)
    for action in repairs.actions:
        print(f"  repair:    {action.action} {action.source}", file=sys.stderr)


def _init_context(
    args: argparse.Namespace,
) -> tuple[Path | None, Path, SkillPlan, init_layout.InitLayout, init_layout.RepairPlan]:
    root = find_repo_root(os.getcwd())
    _warn_stale_plan_dir(root)
    home = Path.home()
    skill_plan = plan_init(args, root, home)
    layout = init_layout.resolve(args, root, skill_plan, home)
    repairs = init_layout.plan_repairs(layout)
    return root, home, skill_plan, layout, repairs


def _check_report(
    args: argparse.Namespace,
    layout: init_layout.InitLayout,
    repairs: init_layout.RepairPlan,
) -> int:
    report = init_layout.inventory(layout)
    report["repairs"] = repairs.to_dict()
    code = 0 if report["clean"] else 1
    if args.json:
        _emit(args, report)
        return code
    print(f"database:  {layout.db}")
    print(f"templates: {layout.templates_dir}")
    print(f"config:    {layout.config or '-'}")
    print(f"skills:    {len(layout.skill_plan.skill_files)} planned")
    print(f"clean:     {'yes' if report['clean'] else 'no'}")
    for item in report["misplaced"]:
        print(f"misplaced: {item}")
    for item in report["missing"]:
        print(f"missing:   {item}")
    for note in report["notes"]:
        print(f"note:      {note}")
    for action in repairs.actions:
        print(f"repair:    {action.action} {action.source}")
    if repairs.stop:
        print(f"stop:      {repairs.stop}")
    return code


def _confirm_init(
    args: argparse.Namespace,
    root: Path | None,
    layout: init_layout.InitLayout,
    repairs: init_layout.RepairPlan,
    interactive: bool,
) -> int | None:
    if getattr(args, "yes", False) or getattr(args, "json", False) or not interactive:
        return None
    _print_layout(layout, repairs)
    if prompt_confirm("Write these resources?"):
        return None
    return _emit(
        args,
        {
            "db": str(layout.db),
            "repo": str(root) if root else None,
            "plan_dir": str(layout.plan_dir),
            "scope": repo_label(layout.db),
            "cancelled": True,
        },
    )


def _stop_init(
    args: argparse.Namespace,
    root: Path | None,
    layout: init_layout.InitLayout,
    repaired: dict,
    stop: str,
) -> int:
    print(f"error: {stop}", file=sys.stderr)
    _emit(
        args,
        {
            "db": str(layout.db),
            "repo": str(root) if root else None,
            "plan_dir": str(layout.plan_dir),
            "scope": repo_label(layout.db),
            "repairs": repaired,
            "error": stop,
        },
    )
    return 1


def _apply_init(
    args: argparse.Namespace,
    root: Path | None,
    home: Path,
    layout: init_layout.InitLayout,
    skill_plan: SkillPlan,
    interactive: bool,
    repaired: dict,
) -> int:
    layout_summary = init_layout.apply_layout(
        layout,
        interactive=interactive,
        read=None,
        write=sys.stderr,
    )
    try:
        store = Store(str(layout.db))
    except (RuntimeError, OSError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    skills_info = apply_skill_plan(skill_plan, root, home)
    gitignored: list[str] = []
    if (
        root is not None
        and layout.gitignore_entries
        and (getattr(args, "yes", False) or interactive)
    ):
        gitignored = [entry for entry in layout.gitignore_entries if append_gitignore(root, entry)]
    return _emit(
        args,
        {
            "db": str(store.path),
            "repo": str(root) if root else None,
            "plan_dir": str(layout.plan_dir),
            "scope": repo_label(store.path),
            "counts": store.counts(),
            "skills": skills_info.to_dict(),
            "templates": layout_summary["templates"],
            "legacy": layout_summary["legacy"],
            "gitignore": {"added": gitignored},
            "layout": layout.to_dict(),
            "notes": init_layout.notes(layout),
            "repairs": repaired,
        },
    )


def _init_error(args: argparse.Namespace, message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    _emit(args, {"error": message})
    return 2


def _check_init_args(args: argparse.Namespace, root: Path | None) -> str | None:
    """Reject flag combinations that cannot honor the chosen scope."""
    if root is not None:
        return None
    if bool(getattr(args, "team", False)):
        return "`--team` needs a git repository"
    scope = str(getattr(args, "skills_scope", "") or "").strip()
    if scope == "project":
        return "`--skills-scope project` needs a git repository"
    return None


def _cmd_init(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    root = find_repo_root(os.getcwd())
    error = _check_init_args(args, root)
    if error is not None:
        return _init_error(args, error)
    root, home, skill_plan, layout, repairs = _init_context(args)
    if getattr(args, "check", False):
        return _check_report(args, layout, repairs)
    interactive = bool(sys.stdin.isatty() and sys.stdout.isatty())
    cancelled = _confirm_init(args, root, layout, repairs, interactive)
    if cancelled is not None:
        return cancelled
    repaired = init_layout.apply_repairs(repairs)
    if repairs.stop:
        return _stop_init(args, root, layout, repaired, repairs.stop)
    return _apply_init(args, root, home, layout, skill_plan, interactive, repaired)


def _cmd_doctor(store: Store | None, args: argparse.Namespace, actor: str) -> int:
    """Read-only init layout report; never opens a database."""
    root = find_repo_root(os.getcwd())
    error = _check_init_args(args, root)
    if error is not None:
        return _init_error(args, error)
    args.check = True
    _, _, _, layout, repairs = _init_context(args)
    return _check_report(args, layout, repairs)


def _cmd_info(store: Store, args: argparse.Namespace, actor: str) -> int:
    root = find_repo_root(os.getcwd())
    plan_dir = store.path.parent
    try:
        contents = sorted(f.name for f in plan_dir.iterdir()) if plan_dir.is_dir() else []
    except OSError:
        contents = []
    return _emit(
        args,
        {
            "db": str(store.path),
            "repo": str(root) if root else None,
            "scope": repo_label(store.path),
            "plan_files": contents,
            "counts": store.counts(),
        },
    )


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
    return _emit(args, {"plan": _ser(vars(p))})


def _cmd_add_milestone(store: Store, args: argparse.Namespace, actor: str) -> int:
    s = services.create_milestone(
        store,
        args.plan,
        args.title,
        args.desc,
        actor=actor,
    )
    return _emit(args, {"milestone": _ser(vars(s))})


def _cmd_add_task(store: Store, args: argparse.Namespace, actor: str) -> int:
    t = services.create_task(
        store,
        args.milestone,
        args.title,
        description=args.desc,
        actor=actor,
    )
    return _emit(args, {"task": _ser(vars(t))})


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
    return _emit(args, {"updated": _ser(vars(updated))})


def _cmd_show(store: Store, args: argparse.Namespace, actor: str) -> int:
    full = store.get_full(args.kind, args.id)
    if full is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if args.json:
        return _emit(args, full)
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
    return _emit(args, {"ok": True, "kind": args.kind, "id": args.id, "to": args.to})


def _cmd_reconcile(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _emit(args, {"reconciled": services.reconcile(store, actor=actor)})


def _cmd_delete(store: Store, args: argparse.Namespace, actor: str) -> int:
    ok = store.delete(args.kind, args.id, actor=actor)
    if not ok:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    return _emit(args, {"ok": True, "deleted": f"{args.kind} #{args.id}"})


def _cmd_add_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    c = store.add_criteria(args.kind, args.id, args.text, actor=actor)
    return _emit(args, {"criteria": vars(c)})


def _cmd_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    found = store.get_parent(args.kind, args.id)
    if found is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    return _emit(args, [vars(c) for c in store.list_criteria(args.kind, args.id)])


def _check_uncheck(store: Store, args: argparse.Namespace, actor: str, done: bool) -> int:
    crit = store.set_criteria(args.id, done, actor=actor)
    if crit is None:
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    return _emit(args, {"criteria": vars(crit)})


def _cmd_check(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, True)


def _cmd_uncheck(store: Store, args: argparse.Namespace, actor: str) -> int:
    return _check_uncheck(store, args, actor, False)


def _cmd_delete_criteria(store: Store, args: argparse.Namespace, actor: str) -> int:
    if not store.delete_criteria(args.id, actor=actor):
        print(msg_not_found("criteria", args.id), file=sys.stderr)
        return 1
    return _emit(args, {"ok": True, "deleted": f"criteria #{args.id}"})


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
    if args.json:
        return _emit(args, matches)
    if not matches:
        print("(no lazyplan references found)")
        return 0
    for match in matches:
        print(f"{match['sha'][:12]} {match['subject']} -> {match['ref']} ({match['action']})")
    return 0


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
    if args.json:
        return _emit(args, entries)
    if not entries:
        print("(no linked repos)")
        return 0
    print(render_forge_status(entries))
    return 0


def _cmd_pr_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    links = store.list_forge_links(args.kind, args.id)
    if args.json:
        return _emit(args, [vars(link) for link in links])
    if not links:
        print("(no pull requests linked)")
        return 0
    print(render_forge_links([vars(link) for link in links]))
    return 0


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
    if args.json:
        return _emit(args, vars(links[0]))
    print(render_forge_links([vars(links[0])]))
    return 0


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
    return _emit(args, {"link": vars(link)})


def _cmd_pr_unlink(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    ok = store.unlink_forge(args.kind, args.id, args.number, actor=actor)
    if not ok:
        print(msg_not_found("pull request", args.number), file=sys.stderr)
        return 1
    return _emit(args, {"ok": True, "unlinked": f"PR #{args.number}"})


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
    return _emit(args, {"link": vars(link)})


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
    return _emit(args, {"ok": True, "unlinked": str(args.sha)})


def _cmd_commits(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    if getattr(args, "refresh", False):
        services.refresh_links(store, args.kind, args.id, actor=actor)
    links = store.effective_links(args.kind, args.id)
    if args.json:
        return _emit(args, [vars(c) for c in links])
    if not links:
        print(EMPTY_COMMITS)
        return 0
    print(render_commits([vars(c) for c in links], files=bool(getattr(args, "files", False))))
    return 0


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
    print(f"started T{result['task']} on {result['branch']} (base {result['base_sha'][:12]})")
    return 0


def _cmd_task_finish(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_task(args.id) is None:
        print(msg_not_found("task", args.id), file=sys.stderr)
        return 1
    result = services.finish_task(
        store,
        args.id,
        repo_path=str(args.repo) if args.repo else "",
        actor=actor,
    )
    if args.json:
        return _emit(args, result)
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
    if not entries:
        if args.json:
            return _emit(args, [])
        print("(no linked repos)")
        return 0
    if args.json:
        return _emit(args, entries)
    print(render_git_status(entries))
    return 0


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
    return _emit(args, {"repo": row})


def _cmd_unlink_repo(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    ok = store.remove_repo_link(args.kind, args.id, str(args.repo), args.remote, actor=actor)
    if not ok:
        print(msg_error(ValueError(f"no such repo link {args.repo!r}")), file=sys.stderr)
        return 1
    return _emit(args, {"ok": True, "unlinked": str(args.repo)})


def _cmd_repos(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    rows = (
        store.effective_repos(args.kind, args.id)
        if getattr(args, "effective", False)
        else store.list_repos(args.kind, args.id)
    )
    if args.json:
        return _emit(args, rows)
    if not rows:
        print(EMPTY_COMMITS)
        return 0
    for r in rows:
        remote = f" ({r['repo_remote']})" if r.get("repo_remote") else ""
        print(f"{r['repo_path']}{remote}")
    return 0


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


def _cmd_feed(store: Store, args: argparse.Namespace, actor: str) -> int:
    seen = -1
    while True:
        events = store.feed(args.limit)
        if args.json or not args.follow:
            if args.follow and args.json:
                fresh = [e for e in events if e["id"] > seen]
                for e in reversed(fresh):
                    print(json.dumps(e, default=str))
                if fresh:
                    seen = max(e["id"] for e in fresh)
            else:
                if args.json:
                    print(json.dumps(events, indent=2, default=str))
                else:
                    if not events:
                        print(EMPTY_FEED)
                    for e in reversed(events):
                        print(f"#{e['id']} [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}")
            if not args.follow:
                return 0
            time.sleep(args.interval)
            continue
        # plain follow: only print new rows
        fresh = [e for e in events if e["id"] > seen]
        for e in reversed(fresh):
            print(
                f"#{e['id']} [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}",
                flush=True,
            )
        if fresh:
            seen = max(e["id"] for e in fresh)
        time.sleep(args.interval)


def _cmd_completion(store: Store, args: argparse.Namespace, actor: str) -> int:
    parser = build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    cmds = list(subs.choices)
    if args.shell == "bash":
        print(f'complete -W "{" ".join(cmds)}" lpui')
        print(f'complete -W "{" ".join(cmds)}" lazyplan')
    else:
        print(f"#compdef lpui lazyplan\n_arguments '1:command:({' '.join(cmds)})'")
    return 0


def _cmd_ui(store: Store, args: argparse.Namespace, actor: str) -> int:
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
    if args.json:
        return _emit(args, payload)
    print(f"upgraded lpui v{installed} -> v{latest} ({info.method})")
    return 0


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
    ("criterion", "add"): "add-criteria",
    ("criterion", "list"): "criteria",
    ("criterion", "tick"): "check",
    ("criterion", "untick"): "uncheck",
    ("criterion", "delete"): "delete-criteria",
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
    "init": _cmd_init,
    "doctor": _cmd_doctor,
    "info": _cmd_info,
    "seed": _cmd_seed,
    "list": _cmd_list,
    "help": _cmd_help,
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
    if args.cmd == "upgrade":
        # Self-upgrade manages the install, not plan data: no database.
        return _cmd_upgrade(None, args, actor)
    if args.cmd is None:
        # Bare `lpui` (or global flags only) opens the standard TUI.
        args.cmd = "ui"
    if args.cmd == "init":
        # Init resolves its own layout; never open a DB before that.
        return _cmd_init(None, args, actor)
    if args.cmd == "doctor":
        return _cmd_doctor(None, args, actor)
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
