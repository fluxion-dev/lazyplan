"""Build the lpui argument parser."""

from __future__ import annotations

import argparse

from .common import _PARSER_DESCRIPTION, _PARSER_EPILOG, global_flags
from .coordination import (
    add_audit,
    add_brief,
    add_claim,
    add_claims,
    add_comment,
    add_context,
    add_dispatch,
    add_hook,
    add_lint,
    add_mcp,
    add_next,
    add_note,
    add_review,
    add_share,
    add_ship,
    add_stats,
    add_sync,
    add_trace,
    add_who,
)
from .maintenance import add_maintenance_group
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
from .questions import add_question_group
from .refs import add_ref_group
from .system import (
    add_completion,
    add_doctor,
    add_help,
    add_info,
    add_notes,
    add_seed,
    add_setup,
    add_ui,
    add_upgrade,
)
from .touch import add_touch_group
from .work import (
    add_list,
    add_noun_groups,
    add_reconcile,
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
    global_flags(p, inherited=False)
    common = argparse.ArgumentParser(add_help=False)
    global_flags(common, inherited=True)
    heal = common.add_mutually_exclusive_group()
    heal.add_argument(
        "--heal",
        dest="heal",
        action="store_true",
        default=argparse.SUPPRESS,
        help="repair parent statuses and leases automatically (default)",
    )
    heal.add_argument(
        "--no-heal",
        dest="heal",
        action="store_false",
        default=argparse.SUPPRESS,
        help="report drift without automatic repair for this command",
    )
    sub = p.add_subparsers(dest="cmd", required=False, title="commands", metavar="COMMAND")
    add_setup(sub, common)
    add_seed(sub, common)
    add_info(sub, common)
    add_doctor(sub, common)
    add_audit(sub, common)
    add_brief(sub, common)
    add_context(sub, common)
    add_review(sub, common)
    add_ship(sub, common)
    add_next(sub, common)
    add_dispatch(sub, common)
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
    add_question_group(sub, common)
    add_ref_group(sub, common)
    add_touch_group(sub, common)
    add_link(sub, common)
    add_unlink(sub, common)
    add_commits(sub, common)
    add_link_repo(sub, common)
    add_unlink_repo(sub, common)
    add_repos(sub, common)
    add_export(sub, common)
    add_import(sub, common)
    add_reconcile(sub, common)
    add_feed(sub, common)
    add_watch(sub, common)
    add_maintenance_group(sub, common)
    add_completion(sub, common)
    add_upgrade(sub, common)
    add_notes(sub, common)
    add_help(sub, common)
    add_ui(sub, common)
    return p
