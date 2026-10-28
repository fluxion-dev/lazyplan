"""Proof CLI commands."""

from __future__ import annotations

import argparse
import json
import sys

from ... import (
    porcelain,
    services,
    textfile,
)
from ...design import (
    EMPTY_COMMITS,
    msg_error,
    msg_no_head,
    msg_no_vcs,
    msg_not_found,
)
from ...forge import RepoRef, parse_pull_url, resolve_auth
from ...github import GitHubClient, GitHubError
from ...render import (
    render_commits,
    render_forge_links,
    render_forge_status,
    render_git_status,
    render_markdown,
)
from ...store import Store, to_payload
from ...vcs import detect_backend, origin_url
from ..emit import (
    _emit,
    _emit_read,
    _emit_record,
    _porcelain_row,
)
from ..rows_proof import (
    _commit_row,
    _git_status_rows,
    _pr_row,
    _pr_status_rows,
    _repo_row,
    _scan_row,
)


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


def _cmd_issue_import(store: Store, args: argparse.Namespace, actor: str) -> int:
    from ... import issues as issues_mod

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
            parsed = issues_mod.parse_linear(json.loads(textfile.read(args.file)))
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
        return _emit(args, {"task": to_payload(vars(task))})
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
        return _emit(args, {"task": to_payload(vars(task))})
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
    from ...render import render_plan_markdown

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
        textfile.write(dest, text + ("" if text.endswith("\n") else "\n"))
        return _emit(args, {"exported": dest})
    print(text)
    return 0


def _cmd_import(store: Store, args: argparse.Namespace, actor: str) -> int:
    import json as _json

    data = _json.loads(textfile.read(args.file))
    try:
        counts = services.import_all(store, data, actor=actor)
    except ValueError as exc:
        print(msg_error(exc), file=sys.stderr)
        return 2
    return _emit(args, {"imported": counts})


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
