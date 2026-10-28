"""CLI command registry."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable

from ...store import Store
from .admin import (
    _cmd_completion,
    _cmd_feed,
    _cmd_help,
    _cmd_info,
    _cmd_seed,
    _cmd_share,
    _cmd_sync,
    _cmd_upgrade,
)
from .admin import (
    _cmd_hook as _cmd_hook,
)
from .admin import (
    _cmd_mcp as _cmd_mcp,
)
from .claim import (
    _cmd_claim,
    _cmd_claims,
    _cmd_next,
)
from .comment import (
    _cmd_comment,
    _cmd_note,
)
from .forge import (
    _cmd_pr_auth,
    _cmd_pr_link,
    _cmd_pr_list,
    _cmd_pr_refresh,
    _cmd_pr_show,
    _cmd_pr_status,
    _cmd_pr_unlink,
)
from .plan import (
    _cmd_add_criteria,
    _cmd_add_milestone,
    _cmd_add_plan,
    _cmd_add_task,
    _cmd_check,
    _cmd_criteria,
    _cmd_criterion_relate,
    _cmd_criterion_unrelate,
    _cmd_delete,
    _cmd_delete_criteria,
    _cmd_list,
    _cmd_reconcile,
    _cmd_show,
    _cmd_status,
    _cmd_uncheck,
    _cmd_update,
)
from .proof import (
    _cmd_commits,
    _cmd_export,
    _cmd_git_scan,
    _cmd_git_status,
    _cmd_import,
    _cmd_issue_import,
    _cmd_link,
    _cmd_link_repo,
    _cmd_repos,
    _cmd_task_block,
    _cmd_task_finish,
    _cmd_task_start,
    _cmd_task_unblock,
    _cmd_unlink,
    _cmd_unlink_repo,
)
from .system import (
    _cmd_audit as _cmd_audit,
)
from .system import (
    _cmd_brief as _cmd_brief,
)
from .system import (
    _cmd_doctor,
    _cmd_lint,
    _cmd_stats,
    _cmd_trace,
)
from .system import (
    _cmd_setup as _cmd_setup,
)
from .ui import (
    _cmd_ui,
)

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

_COMMANDS: dict[str, Callable[[Store, Namespace, str], int]] = {
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
