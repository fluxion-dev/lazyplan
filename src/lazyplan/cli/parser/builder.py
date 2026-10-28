"""Build the lpui argument parser."""

from __future__ import annotations

import argparse

from ...store import default_actor
from .common import _PARSER_DESCRIPTION, _PARSER_EPILOG
from .coordination import (
    add_audit,
    add_brief,
    add_claim,
    add_claims,
    add_comment,
    add_hook,
    add_lint,
    add_mcp,
    add_next,
    add_note,
    add_share,
    add_stats,
    add_sync,
    add_trace,
    add_who,
)
from .proof import (
    add_commits,
    add_export,
    add_feed,
    add_import,
    add_link,
    add_link_repo,
    add_repos,
    add_unlink,
    add_unlink_repo,
    add_watch,
)
from .system import (
    add_completion,
    add_doctor,
    add_help,
    add_info,
    add_seed,
    add_setup,
    add_ui,
    add_upgrade,
)
from .work import (
    add_add_criteria,
    add_add_milestone,
    add_add_plan,
    add_add_task,
    add_criteria,
    add_criterion_groups,
    add_delete,
    add_delete_criteria,
    add_list,
    add_noun_groups,
    add_reconcile,
    add_show,
    add_status,
    add_update,
)


def build_parser() -> argparse.ArgumentParser:
    """lpui argument parser; globals repeat on every subcommand."""
    p = argparse.ArgumentParser(
        description=_PARSER_DESCRIPTION,
        epilog=_PARSER_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="which database file to use (default: $LAZYPLAN_DB, else ./.agents/lazyplan/ in a repo, else the global one)",
    )
    p.add_argument(
        "--json", action="store_true", help="print output as JSON so scripts and agents can read it"
    )
    p.add_argument(
        "--porcelain",
        action="store_true",
        help="print terse tab-separated rows for active agents (--json still wins)",
    )
    p.add_argument("--version", action="store_true", help="print the installed version and exit")
    p.add_argument(
        "--actor",
        default=default_actor(),
        metavar="NAME",
        help="who is making this change (you see it in feed; default: your login name or 'human')",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print output as JSON so scripts and agents can read it",
    )
    common.add_argument(
        "--porcelain",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print terse tab-separated rows for active agents (--json still wins)",
    )
    common.add_argument(
        "--version",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the installed version and exit",
    )
    common.add_argument(
        "--actor",
        default=argparse.SUPPRESS,
        metavar="NAME",
        help="who made this change (you see it in feed)",
    )
    sub = p.add_subparsers(dest="cmd", required=False, title="commands", metavar="COMMAND")
    add_setup(sub, common)
    add_seed(sub, common)
    add_info(sub, common)
    add_doctor(sub, common)
    add_audit(sub, common)
    add_brief(sub, common)
    add_next(sub, common)
    add_claim(sub, common)
    add_note(sub, common)
    add_claims(sub, common)
    add_who(sub, common)
    add_stats(sub, common)
    add_lint(sub, common)
    add_sync(sub, common)
    add_share(sub, common)
    add_comment(sub, common)
    add_mcp(sub, common)
    add_trace(sub, common)
    add_hook(sub, common)
    add_list(sub, common)
    add_noun_groups(sub, common)
    add_add_plan(sub, common)
    add_add_milestone(sub, common)
    add_add_task(sub, common)
    add_update(sub, common)
    add_show(sub, common)
    add_add_criteria(sub, common)
    add_criteria(sub, common)
    add_criterion_groups(sub, common)
    add_delete_criteria(sub, common)
    add_link(sub, common)
    add_unlink(sub, common)
    add_commits(sub, common)
    add_link_repo(sub, common)
    add_unlink_repo(sub, common)
    add_repos(sub, common)
    add_export(sub, common)
    add_import(sub, common)
    add_status(sub, common)
    add_reconcile(sub, common)
    add_delete(sub, common)
    add_feed(sub, common)
    add_watch(sub, common)
    add_completion(sub, common)
    add_upgrade(sub, common)
    add_help(sub, common)
    add_ui(sub, common)
    return p
