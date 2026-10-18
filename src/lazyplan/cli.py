"""`lpui` companion CLI (`lazyplan` is the same binary). Human + agent ingress:
every mutation writes SQLite; the running TUI auto-refreshes. Stdlib only
(no Textual import here)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .cli_parser import build_parser
from .design import (
    EMPTY_FEED,
    EMPTY_NO_PROJECTS,
    HELP_TEXT,
    msg_error,
    msg_not_found,
)
from .gantt import bar, span
from .models import Project, Status, Task, UserStory
from .render import render_full, render_markdown, tree_lines
from .repo import ensure_plan_dir, find_repo_root, repo_label
from .seed import seed as seed_demo
from .skills import handle_init as _init_skills
from .store import Store, _ser


def _emit(args: argparse.Namespace, payload: object) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Dispatch one lpui invocation; exit codes are agent-readable."""
    args = build_parser().parse_args(argv)
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
            return _emit(
                args,
                {
                    "db": str(store.path),
                    "repo": str(root) if root else None,
                    "plan_dir": str(plan_dir),
                    "scope": repo_label(store.path),
                    "counts": store.counts(),
                    "skills": skills_info,
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
            status = Status(args.status) if args.status else None
            if args.json:
                payload = [
                    {
                        "project": _ser(vars(p)),
                        "stories": [
                            {
                                "story": _ser(vars(s)),
                                "links": [vars(li) for li in store.list_links("story", s.id)],
                                "criteria": [vars(c) for c in store.list_criteria("story", s.id)],
                                "tasks": [
                                    {
                                        "task": _ser(vars(t)),
                                        "links": [
                                            vars(li) for li in store.list_links("task", t.id)
                                        ],
                                        "criteria": [
                                            vars(c) for c in store.list_criteria("task", t.id)
                                        ],
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
                        owner=args.owner,
                        priority=args.priority,
                    )
                ]
                return _emit(args, payload)
            lines = tree_lines(store, status, args.project, args.owner, args.priority)
            print("\n".join(lines) if lines else EMPTY_NO_PROJECTS)
            return 0
        if args.cmd == "gantt":
            status = Status(args.status) if args.status else None
            tree = store.tree(
                status=status, project_id=args.project, owner=args.owner, priority=args.priority
            )
            ms_by_project: dict[int, list] = {}
            dates = []
            for _, stories in tree:
                for s, tasks in stories:
                    dates += [s.start_date, s.end_date]
                    if args.tasks:
                        for t in tasks:
                            dates += [t.start_date, t.end_date]
            if args.project is not None:
                ms_by_project[args.project] = store.list_milestones(args.project)
            else:
                for p, _ in tree:
                    ms_by_project[p.id] = store.list_milestones(p.id)
            for ms in ms_by_project.values():
                dates += [m.date for m in ms if m.date]
            dates = [d for d in dates if d]
            lo, hi = span(dates, args.width)
            print(f"{lo} .. {hi} (w={args.width})")
            for p, stories in tree:
                print(f"P#{p.id} {p.name}")
                crit_ids = set(store.critical_path(p.id))
                for m in ms_by_project.get(p.id, []):
                    print(f"  ◆ {m.date or '????-??-??'} M#{m.id} {m.title}")
                for s, tasks in stories:
                    mark = ("*" if s.id in crit_ids else " ") + (
                        "!" if store.is_blocked("story", s.id) else " "
                    )
                    print(
                        f"{mark} S#{s.id:>3} {bar(s.start_date, s.end_date, lo, hi, args.width)} {s.title} [{s.status.value}]"
                    )
                    if args.tasks:
                        for t in tasks:
                            tmark = " " + ("!" if store.is_blocked("task", t.id) else " ")
                            b = (
                                bar(t.start_date, t.end_date, lo, hi, args.width)
                                if (t.start_date and t.end_date)
                                else "(no dates)"
                            )
                            print(f"{tmark} T#{t.id:>3} {b} {t.title} [{t.status.value}]")
            if not tree:
                print(EMPTY_NO_PROJECTS)
            return 0
        if args.cmd == "help":
            if args.json:
                return _emit(args, {"help": HELP_TEXT})
            print(HELP_TEXT)
            return 0
        if args.cmd == "add-project":
            p = store.add_project(
                args.name,
                args.desc,
                args.start,
                args.end,
                goal=args.goal,
                success_metrics=args.metrics,
                scope_in=args.scope_in,
                scope_out=args.scope_out,
                assumptions=args.assumptions,
                actor=actor,
            )
            return _emit(args, {"project": _ser(vars(p))})
        if args.cmd == "add-story":
            s = store.add_story(
                args.project,
                args.title,
                args.desc,
                args.start,
                args.end,
                owner=args.owner,
                priority=args.priority,
                labels=args.labels,
                estimate=args.estimate,
                blocked_by=args.blocked_by,
                actor=actor,
            )
            return _emit(args, {"story": _ser(vars(s))})
        if args.cmd == "add-task":
            t = store.add_task(
                args.story,
                args.title,
                args.estimate,
                args.start,
                args.end,
                description=args.desc,
                owner=args.owner,
                priority=args.priority,
                labels=args.labels,
                blocked_by=args.blocked_by,
                actor=actor,
            )
            return _emit(args, {"task": _ser(vars(t))})
        if args.cmd == "update":
            title = args.title or args.name
            priority = (
                None
                if args.priority is None
                else ("" if args.priority == "none" else args.priority)
            )
            updated: Project | UserStory | Task | None = None
            if args.kind == "project":
                updated = store.update_project(
                    args.id,
                    name=title,
                    description=args.desc,
                    start_date=args.start,
                    end_date=args.end,
                    goal=args.goal,
                    success_metrics=args.metrics,
                    scope_in=args.scope_in,
                    scope_out=args.scope_out,
                    assumptions=args.assumptions,
                    actor=actor,
                )
            elif args.kind == "story":
                updated = store.update_story(
                    args.id,
                    title=title,
                    description=args.desc,
                    start_date=args.start,
                    end_date=args.end,
                    owner=args.owner,
                    priority=priority,
                    labels=args.labels,
                    estimate=args.estimate,
                    blocked_by=args.blocked_by,
                    actor=actor,
                )
            else:
                updated = store.update_task(
                    args.id,
                    title=title,
                    estimate=args.estimate,
                    start_date=args.start,
                    end_date=args.end,
                    description=args.desc,
                    owner=args.owner,
                    priority=priority,
                    labels=args.labels,
                    blocked_by=args.blocked_by,
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
        if args.cmd == "add-link":
            link = store.add_link(args.kind, args.id, args.url, args.label, actor=actor)
            return _emit(args, {"link": vars(link)})
        if args.cmd == "links":
            found = store.get_story(args.id) if args.kind == "story" else store.get_task(args.id)
            if found is None:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            return _emit(args, [vars(li) for li in store.list_links(args.kind, args.id)])
        if args.cmd == "delete-link":
            if not store.delete_link(args.id, actor=actor):
                print(msg_not_found("link", args.id), file=sys.stderr)
                return 1
            return _emit(args, {"ok": True, "deleted": f"link #{args.id}"})
        if args.cmd == "status":
            if args.to == "done" and args.kind in ("story", "task"):
                left = store.open_criteria(args.kind, args.id)
                if left:
                    print(
                        f"warning: {len(left)} open acceptance criteria "
                        f"({', '.join(c.text[:40] for c in left[:3])}); closing anyway",
                        file=sys.stderr,
                    )
            ok = store.set_status(args.kind, args.id, Status(args.to), actor=actor)
            if not ok:
                print(msg_not_found(args.kind, args.id), file=sys.stderr)
                return 1
            return _emit(args, {"ok": True, "kind": args.kind, "id": args.id, "to": args.to})
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
            found = store.get_story(args.id) if args.kind == "story" else store.get_task(args.id)
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
        if args.cmd == "add-risk":
            from .models import RiskStatus as _RS

            r = store.add_risk(
                args.project, args.title, args.likelihood, args.impact, args.mitigation, actor=actor
            )
            d = vars(r)
            d["status"] = r.status.value
            return _emit(args, {"risk": d})
        if args.cmd == "risks":
            if store.get_project(args.project) is None:
                print(msg_not_found("project", args.project), file=sys.stderr)
                return 1
            return _emit(args, [store._risk_to_dict(r) for r in store.list_risks(args.project)])
        if args.cmd == "risk-status":
            from .models import RiskStatus as _RS

            to = _RS(args.to) if args.to else None
            risk = store.set_risk(args.id, status=to, mitigation=args.mitigation, actor=actor)
            if risk is None:
                print(msg_not_found("risk", args.id), file=sys.stderr)
                return 1
            return _emit(args, {"risk": store._risk_to_dict(risk)})
        if args.cmd == "add-milestone":
            m = store.add_milestone(args.project, args.title, args.date, actor=actor)
            return _emit(args, {"milestone": vars(m)})
        if args.cmd == "milestones":
            if store.get_project(args.project) is None:
                print(msg_not_found("project", args.project), file=sys.stderr)
                return 1
            return _emit(args, [vars(m) for m in store.list_milestones(args.project)])
        if args.cmd == "delete-milestone":
            if not store.delete_milestone(args.id, actor=actor):
                print(msg_not_found("milestone", args.id), file=sys.stderr)
                return 1
            return _emit(args, {"ok": True, "deleted": f"milestone #{args.id}"})
        if args.cmd == "propose":
            fields = {
                "title": args.title,
                "description": args.desc,
                "owner": args.owner,
                "priority": args.priority,
                "labels": args.labels,
                "estimate": args.estimate,
                "start_date": args.start,
                "end_date": args.end,
                "blocked_by": args.blocked_by,
            }
            return _emit(args, store.propose(args.kind, args.parent, fields, actor=actor))
        if args.cmd == "proposals":
            return _emit(args, store.list_proposals(args.status))
        if args.cmd in ("approve", "reject"):
            try:
                res = store.decide_proposal(args.id, args.cmd == "approve", actor=actor)
            except ValueError as exc:
                print(msg_error(exc), file=sys.stderr)
                return 2
            if res is None:
                print(msg_not_found("proposal", args.id), file=sys.stderr)
                return 1
            return _emit(args, res)
        if args.cmd == "ask":
            return _emit(args, store.ask(actor, args.question))
        if args.cmd == "questions":
            return _emit(args, store.list_questions(open_only=not args.all))
        if args.cmd == "answer":
            res = store.answer_question(args.id, args.text, actor=actor)
            if res is None:
                print(msg_not_found("question", args.id), file=sys.stderr)
                return 1
            return _emit(args, res)
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
        if args.cmd == "sync":
            import os as _os

            dsn = args.dsn.strip() or _os.environ.get("LAZYPLAN_PG_DSN", "").strip()
            if not dsn:
                print("need --dsn or $LAZYPLAN_PG_DSN", file=sys.stderr)
                return 2
            from .postgres_sync import sync_sqlite_to_pg

            try:
                counts = sync_sqlite_to_pg(str(store.path), dsn)
            except RuntimeError as exc:
                print(msg_error(exc), file=sys.stderr)
                return 2
            return _emit(args, {"synced_to": dsn.split("@")[-1], "counts": counts})
        if args.cmd == "completion":
            cmds = [
                "init",
                "seed",
                "list",
                "gantt",
                "add-project",
                "add-story",
                "add-task",
                "update",
                "show",
                "add-link",
                "links",
                "delete-link",
                "add-criteria",
                "criteria",
                "check",
                "uncheck",
                "delete-criteria",
                "add-risk",
                "risks",
                "risk-status",
                "add-milestone",
                "milestones",
                "delete-milestone",
                "propose",
                "proposals",
                "approve",
                "reject",
                "ask",
                "questions",
                "answer",
                "export",
                "import",
                "sync",
                "status",
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
