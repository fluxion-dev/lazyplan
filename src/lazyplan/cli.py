"""`lpui` companion CLI (`lazyplan` is the same binary). Human + agent ingress:
every mutation writes SQLite; the running TUI auto-refreshes. Stdlib only
(no Textual import here)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .cli_parser import build_parser, package_version
from .design import (
    EMPTY_COMMITS,
    EMPTY_FEED,
    EMPTY_NO_PROJECTS,
    HELP_TEXT,
    msg_error,
    msg_no_head,
    msg_no_vcs,
    msg_not_found,
)
from .models import Project, Status, Task, UserStory
from .render import render_commits, render_full, render_markdown, tree_lines
from .repo import (
    ensure_plan_dir,
    find_repo_root,
    legacy_plan_dir,
    move_legacy_plan_dir,
    repo_label,
)
from .seed import seed as seed_demo
from .skills import append_gitignore, prompt_confirm
from .skills import handle_init as _init_skills
from .store import Store, _ser
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
    """Offer to move legacy `.plan/` to `.lazyplan/` on a TTY; new dir or None."""
    if root is None:
        return None
    if Path(db_path).expanduser().parent != legacy_plan_dir(root):
        return None
    if not sys.stdin.isatty():
        return None
    if not prompt_confirm("Move legacy .plan/ to .lazyplan/"):
        return None
    return move_legacy_plan_dir(root)


def _gitignore_entries(root: Path | None, plan_dir: Path, skills_info: dict) -> list[str]:
    """Repo-local dirs this init created, as .gitignore entries."""
    if root is None:
        return []
    entries: list[str] = []
    if Path(plan_dir).expanduser().parent == Path(root).expanduser():
        entries.append(Path(plan_dir).name + "/")
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
        if args.cmd == "init":
            plan_dir = ensure_plan_dir(store.path)
            root = find_repo_root(os.getcwd())
            skills_info = _init_skills(args, root)
            # Only the repo's own default dir gets migrated, never an explicit --db.
            if args.db is None and not os.environ.get("LAZYPLAN_DB", "").strip():
                if _maybe_move_legacy_plan_dir(root, store.path) is not None:
                    store = Store(args.db)
                    plan_dir = ensure_plan_dir(store.path)
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
                    "gitignore": {"added": gitignored},
                },
            )
        if args.cmd == "info":
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
        if args.cmd == "seed":
            seed_demo(store)
            return _emit(args, {"db": str(store.path), "counts": store.counts()})
        if args.cmd == "list":
            if args.archived:
                archived, status = "only", None
            elif args.status is None:
                archived, status = "hide", None
            elif args.status == "all":
                archived, status = "show", None
            else:
                archived, status = "hide", Status(args.status)
            if args.json:
                payload = [
                    {
                        "project": _ser(vars(p)),
                        "criteria": [vars(c) for c in store.list_criteria("project", p.id)],
                        "links": [vars(c) for c in store.list_links("project", p.id)],
                        "stories": [
                            {
                                "story": _ser(vars(s)),
                                "criteria": [vars(c) for c in store.list_criteria("story", s.id)],
                                "links": [vars(c) for c in store.list_links("story", s.id)],
                                "tasks": [
                                    {
                                        "task": _ser(vars(t)),
                                        "criteria": [
                                            vars(c) for c in store.list_criteria("task", t.id)
                                        ],
                                        "links": [vars(c) for c in store.list_links("task", t.id)],
                                    }
                                    for t in ts
                                ],
                            }
                            for s, ts in stories
                        ],
                    }
                    for p, stories in store.tree(
                        status=status,
                        project_id=args.project,
                        priority=args.priority,
                        archived=archived,
                    )
                ]
                return _emit(args, payload)
            lines = tree_lines(
                store, status, args.project, args.priority, dot=_tty_dot(args), archived=archived
            )
            print("\n".join(lines) if lines else EMPTY_NO_PROJECTS)
            return 0
        if args.cmd == "help":
            if args.json:
                return _emit(args, {"help": HELP_TEXT})
            print(HELP_TEXT)
            return 0
        if args.cmd == "add-project":
            title = _resolve_title(args)
            if not title.strip():
                print("error: add-project needs --title", file=sys.stderr)
                return 2
            desc = args.desc if args.desc is not None else (args.what or "")
            goal = args.goal if args.goal is not None else (args.why or "")
            p = store.add_project(
                title,
                desc,
                goal=goal,
                priority=args.priority,
                actor=actor,
            )
            return _emit(args, {"project": _ser(vars(p))})
        if args.cmd == "add-story":
            s = store.add_story(
                args.project,
                args.title,
                args.desc,
                priority=args.priority,
                actor=actor,
            )
            return _emit(args, {"story": _ser(vars(s))})
        if args.cmd == "add-task":
            t = store.add_task(
                args.story,
                args.title,
                description=args.desc,
                priority=args.priority,
                actor=actor,
            )
            return _emit(args, {"task": _ser(vars(t))})
        if args.cmd == "update":
            title_patch = _resolve_title(args) or None
            desc_patch: str | None = args.desc if args.desc is not None else args.what
            priority = (
                None
                if args.priority is None
                else ("" if args.priority == "none" else args.priority)
            )
            updated: Project | UserStory | Task | None = None
            if args.kind == "project":
                goal = args.goal if args.goal is not None else args.why
                updated = store.update_project(
                    args.id,
                    name=title_patch,
                    description=desc_patch,
                    goal=goal,
                    priority=priority,
                    actor=actor,
                )
            elif args.kind == "story":
                updated = store.update_story(
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
        if args.cmd == "show":
            full = store.get_full(args.kind, args.id)
            if full is None:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            if args.json:
                return _emit(args, full)
            print(render_full(args.kind, full))
            return 0
        if args.cmd == "status":
            left = store.open_criteria(args.kind, args.id)
            if args.to == "done" and left:
                print(
                    f"warning: {len(left)} open acceptance criteria "
                    f"({', '.join(c.text[:40] for c in left[:3])}); closing anyway",
                    file=sys.stderr,
                )
            ok = store.set_status(args.kind, args.id, Status(args.to), actor=actor)
            if not ok:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            if args.to == "done":
                _auto_link_head(store, args.kind, args.id, actor)
            return _emit(args, {"ok": True, "kind": args.kind, "id": args.id, "to": args.to})
        if args.cmd == "reconcile":
            return _emit(args, {"reconciled": store.reconcile(actor=actor)})
        if args.cmd == "delete":
            ok = store.delete(args.kind, args.id, actor=actor)
            if not ok:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            return _emit(args, {"ok": True, "deleted": f"{args.kind} #{args.id}"})
        if args.cmd == "add-criteria":
            c = store.add_criteria(args.kind, args.id, args.text, actor=actor)
            return _emit(args, {"criteria": vars(c)})
        if args.cmd == "criteria":
            found = store.get_parent(args.kind, args.id)
            if found is None:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            return _emit(args, [vars(c) for c in store.list_criteria(args.kind, args.id)])
        if args.cmd in ("check", "uncheck"):
            crit = store.set_criteria(args.id, args.cmd == "check", actor=actor)
            if crit is None:
                print(msg_not_found("criteria", args.id), file=sys.stderr)
                return 1
            return _emit(args, {"criteria": vars(crit)})
        if args.cmd == "delete-criteria":
            if not store.delete_criteria(args.id, actor=actor):
                print(msg_not_found("criteria", args.id), file=sys.stderr)
                return 1
            return _emit(args, {"ok": True, "deleted": f"criteria #{args.id}"})
        if args.cmd == "link":
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
        if args.cmd == "unlink":
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
        if args.cmd == "commits":
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
        if args.cmd == "export":
            data = store.export_all()
            if args.format == "json":
                return _emit(args, data)
            print(render_markdown(data))
            return 0
        if args.cmd == "import":
            import json as _json

            with open(args.file) as fh:
                data = _json.load(fh)
            try:
                counts = store.import_all(data, actor=actor)
            except ValueError as exc:
                print(msg_error(exc), file=sys.stderr)
                return 2
            return _emit(args, {"imported": counts})
        if args.cmd == "feed":
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
                                print(
                                    f"#{e['id']} [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
                                )
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
        if args.cmd == "completion":
            cmds = [
                "init",
                "seed",
                "list",
                "add-project",
                "add-story",
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
        if args.cmd == "ui":
            from .tui import run

            return run(db_path=args.db)
    except (ValueError, KeyError) as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
