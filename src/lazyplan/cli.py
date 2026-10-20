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

from . import services
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
from .models import Milestone, Plan, Status, Task
from .render import render_commits, render_full, render_markdown, tree_lines
from .repo import (
    LEGACY_PLAN_DIR,
    ensure_plan_dir,
    find_repo_root,
    is_repo_plan_dir,
    legacy_plan_dir,
    move_legacy_plan_dir,
    repo_label,
    stale_plan_dirs,
)
from .seed import seed as seed_demo
from .skills import append_gitignore, prompt_confirm
from .skills import handle_init as _init_skills
from .store import Store, _ser
from .templates import run_template_setup
from .vcs import current_head, detect_backend


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


def _auto_link_head(store: Store, kind: str, obj_id: int, actor: str) -> None:
    """Best-effort HEAD capture on status->done. Silent outside git or with no HEAD."""
    try:
        _backend, info = current_head(".")
    except Exception:
        return
    if info is None:
        return
    try:
        existing = store.list_links(kind, obj_id)
    except (ValueError, KeyError):
        return
    if any(link.sha == info.sha for link in existing):
        return
    try:
        store.link_commit(
            kind,
            obj_id,
            info.sha,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            actor=actor,
        )
    except (ValueError, KeyError):
        return


def _maybe_move_legacy_plan_dir(root: Path | None, db_path: Path) -> Path | None:
    """Offer to move legacy `.plan/` to `.agents/lazyplan/` on a TTY; new dir or None."""
    if root is None:
        return None
    if Path(db_path).expanduser().parent != legacy_plan_dir(root):
        return None
    if not sys.stdin.isatty():
        return None
    if not prompt_confirm("Move legacy .plan/ to .agents/lazyplan/"):
        return None
    return move_legacy_plan_dir(root)


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


def _gitignore_entries(root: Path | None, plan_dir: Path, skills_info: dict) -> list[str]:
    """Repo-local dirs this init created, as .gitignore entries."""
    if root is None:
        return []
    entries: list[str] = []
    try:
        rel = Path(plan_dir).expanduser().relative_to(Path(root).expanduser())
    except ValueError:
        rel = None
    if rel is not None and str(rel) != ".":
        entries.append(rel.as_posix() + "/")
    for line in skills_info.get("installed", []):
        if not str(line).endswith("(wrote)"):
            continue
        dest = str(line).rsplit(" (", 1)[0]
        try:
            rel = Path(dest).relative_to(root)
        except ValueError:
            continue
        entries.append(rel.parent.as_posix() + "/")
    return list(dict.fromkeys(entries))


def _maybe_offer_gitignore(
    args: argparse.Namespace, root: Path | None, plan_dir: Path, skills_info: dict
) -> list[str]:
    """Add .gitignore entries for created repo-local dirs. Returns added entries."""
    if root is None:
        return []
    entries = _gitignore_entries(root, plan_dir, skills_info)
    if not entries:
        return []
    if getattr(args, "yes", False):
        return [e for e in entries if append_gitignore(root, e)]
    if getattr(args, "json", False) or not sys.stdin.isatty():
        return []
    return [
        e
        for e in entries
        if prompt_confirm(f"Add {e} to .gitignore?") and append_gitignore(root, e)
    ]


def _cmd_init(store: Store, args: argparse.Namespace, actor: str) -> int:
    plan_dir = ensure_plan_dir(store.path)
    root = find_repo_root(os.getcwd())
    _warn_stale_plan_dir(root)
    # Only the repo's own default dir gets migrated, never an explicit --db.
    # Migrate before skill/template setup so the wizard writes final paths.
    if args.db is None and not os.environ.get("LAZYPLAN_DB", "").strip():
        if _maybe_move_legacy_plan_dir(root, store.path) is not None:
            store = Store(args.db)
            plan_dir = ensure_plan_dir(store.path)
    skills_info = _init_skills(args, root, plan_dir=plan_dir)
    summary = skills_info.get("templates")
    if summary is None:
        if is_repo_plan_dir(plan_dir) or plan_dir.name == LEGACY_PLAN_DIR:
            summary = run_template_setup(plan_dir, interactive=False)
        else:
            summary = {"added": [], "kept": [], "reset": []}
    gitignored = _maybe_offer_gitignore(args, root, plan_dir, skills_info)
    return _emit(
        args,
        {
            "db": str(store.path),
            "repo": str(root) if root else None,
            "plan_dir": str(plan_dir),
            "scope": repo_label(store.path),
            "counts": store.counts(),
            "skills": skills_info,
            "templates": summary,
            "gitignore": {"added": gitignored},
        },
    )


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


def _cmd_list(store: Store, args: argparse.Namespace, actor: str) -> int:
    if args.archived:
        archived, status = "only", None
    elif args.status is None:
        archived, status = "hide", None
    elif args.status == "all":
        archived, status = "show", None
    else:
        archived, status = "hide", Status(args.status)
    if args.plan is not None or args.all:
        limit = None
    elif args.json:
        limit = args.limit
    else:
        limit = args.limit if args.limit is not None else services.DEFAULT_PLAN_LIMIT
    if args.json:
        payload = [
            {
                "plan": _ser(vars(p)),
                "criteria": [vars(c) for c in store.list_criteria("plan", p.id)],
                "links": [vars(c) for c in store.list_links("plan", p.id)],
                "milestones": [
                    {
                        "milestone": _ser(vars(s)),
                        "criteria": [vars(c) for c in store.list_criteria("milestone", s.id)],
                        "links": [vars(c) for c in store.list_links("milestone", s.id)],
                        "tasks": [
                            {
                                "task": _ser(vars(t)),
                                "criteria": [vars(c) for c in store.list_criteria("task", t.id)],
                                "links": [vars(c) for c in store.list_links("task", t.id)],
                            }
                            for t in ts
                        ],
                    }
                    for s, ts in milestones
                ],
            }
            for p, milestones in services.tree(
                store,
                status=status,
                plan_id=args.plan,
                priority=args.priority,
                archived=archived,
                limit=limit,
            )
        ]
        return _emit(args, payload)
    lines = tree_lines(
        store,
        status,
        args.plan,
        args.priority,
        dot=_tty_dot(args),
        archived=archived,
        limit=limit,
    )
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
        print("error: add-plan needs --title", file=sys.stderr)
        return 2
    desc = args.desc if args.desc is not None else (args.what or "")
    goal = args.goal if args.goal is not None else (args.why or "")
    p = services.create_plan(
        store,
        title,
        desc,
        goal=goal,
        priority=args.priority,
        actor=actor,
    )
    return _emit(args, {"plan": _ser(vars(p))})


def _cmd_add_milestone(store: Store, args: argparse.Namespace, actor: str) -> int:
    s = services.create_milestone(
        store,
        args.plan,
        args.title,
        args.desc,
        priority=args.priority,
        actor=actor,
    )
    return _emit(args, {"milestone": _ser(vars(s))})


def _cmd_add_task(store: Store, args: argparse.Namespace, actor: str) -> int:
    t = services.create_task(
        store,
        args.milestone,
        args.title,
        description=args.desc,
        priority=args.priority,
        actor=actor,
    )
    return _emit(args, {"task": _ser(vars(t))})


def _cmd_update(store: Store, args: argparse.Namespace, actor: str) -> int:
    title_patch = _resolve_title(args) or None
    desc_patch: str | None = args.desc if args.desc is not None else args.what
    priority = None if args.priority is None else ("" if args.priority == "none" else args.priority)
    updated: Plan | Milestone | Task | None = None
    if args.kind == "plan":
        goal = args.goal if args.goal is not None else args.why
        updated = store.update_plan(
            args.id,
            name=title_patch,
            description=desc_patch,
            goal=goal,
            priority=priority,
            actor=actor,
        )
    elif args.kind == "milestone":
        updated = store.update_milestone(
            args.id,
            title=title_patch,
            description=desc_patch,
            priority=priority,
            actor=actor,
        )
    else:
        updated = store.update_task(
            args.id,
            title=title_patch,
            description=desc_patch,
            priority=priority,
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
    print(render_full(args.kind, full))
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
        _auto_link_head(store, args.kind, args.id, actor)
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


def _cmd_link(store: Store, args: argparse.Namespace, actor: str) -> int:
    if store.get_parent(args.kind, args.id) is None:
        print(msg_not_found(args.kind, args.id), file=sys.stderr)
        return 1
    backend, root = detect_backend(".")
    if backend is None or root is None:
        print(msg_no_vcs(), file=sys.stderr)
        return 2
    if getattr(args, "sha", None):
        info = backend.show(root, str(args.sha))
        if info is None:
            print(msg_error(ValueError(f"unknown commit {args.sha!r}")), file=sys.stderr)
            return 2
    else:
        _, info = current_head(".")
        if info is None:
            print(msg_no_head(), file=sys.stderr)
            return 2
    link = store.link_commit(
        args.kind,
        args.id,
        info.sha,
        subject=info.subject,
        author=info.author,
        timestamp=info.timestamp,
        repo_root=info.repo_root,
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
    backend, _root = detect_backend(".")
    links = [] if backend is None else store.list_links(args.kind, args.id)
    if args.json:
        return _emit(args, [vars(c) for c in links])
    if not links:
        print(EMPTY_COMMITS)
        return 0
    print(render_commits([vars(c) for c in links]))
    return 0


def _cmd_export(store: Store, args: argparse.Namespace, actor: str) -> int:
    data = services.export_all(store)
    if args.format == "json":
        return _emit(args, data)
    print(render_markdown(data))
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
    cmds = [
        "init",
        "seed",
        "list",
        "add-plan",
        "add-milestone",
        "add-task",
        "update",
        "show",
        "add-criteria",
        "criteria",
        "check",
        "uncheck",
        "delete-criteria",
        "link",
        "unlink",
        "commits",
        "export",
        "import",
        "status",
        "reconcile",
        "delete",
        "feed",
        "watch",
        "info",
        "help",
        "ui",
        "completion",
    ]
    if args.shell == "bash":
        print(f'complete -W "{" ".join(cmds)}" lpui')
        print(f'complete -W "{" ".join(cmds)}" lazyplan')
    else:
        print(f"#compdef lpui lazyplan\n_arguments '1:command:({' '.join(cmds)})'")
    return 0


def _cmd_ui(store: Store, args: argparse.Namespace, actor: str) -> int:
    from .tui import run

    return run(db_path=args.db)


_COMMANDS: dict[str, Callable[[Store, argparse.Namespace, str], int]] = {
    "init": _cmd_init,
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
    "export": _cmd_export,
    "import": _cmd_import,
    "feed": _cmd_feed,
    "completion": _cmd_completion,
    "ui": _cmd_ui,
}


def main(argv: list[str] | None = None) -> int:
    """Dispatch one lpui invocation; exit codes are agent-readable."""
    args = build_parser().parse_args(argv)
    if getattr(args, "version", False):
        # Before Store(): printing the version must not create a DB.
        print(package_version())
        return 0
    if args.cmd is None:
        # Bare `lpui` (or global flags only) opens the standard TUI.
        args.cmd = "ui"
    # `watch` is `feed --follow`
    if args.cmd == "watch":
        args.cmd = "feed"
        args.follow = True
        args.interval = 1.0
        args.json = getattr(args, "json", False)
    store = Store(args.db)
    actor = getattr(args, "actor", "human")
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
