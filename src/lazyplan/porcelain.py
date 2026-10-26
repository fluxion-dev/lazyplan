"""Porcelain output: stable tab-separated records for active agents.

Rows are one line, no header, no glyphs, no ANSI, and no blank lines:

    kind<TAB>id<TAB>status<TAB>title<TAB>parent<TAB>extra

`parent` is `-` or `kind:id` (for example `plan:12`). `extra` is progress
(`done/total`) for plans and milestones, `blocked` on a blocked task, a
documented detail on some read rows, and `-` elsewhere. Criterion rows use
`kind=criterion`, status `open|done`, and parent `kind:id`. Write
confirmations reuse the same six columns:

- `commit`: id is the full SHA, status `linked|unlinked`, title the subject.
- `repo`: id is the checkout path, title the remote (or `-`).
- `pr`: id is the pull request number, title the URL.
- `claim`: id is the task, status the actor, title the task, extra the expiry.
- `note`: id is the note, status the actor, title the text, extra the timestamp.
- `link`: id is the criterion, status `linked|unlinked`, title the task, parent
  `criterion:<id>`, extra `task:<id>`.
- `trace`: id is the criterion, status `proves|missing`, title the task, parent
  `criterion:<id>`, extra `task:<id>`.
- `lint`: id is the rule, status `error|warn`, title the message, parent
  `kind:id`.
- `task start`, `task finish`, `block`, and `unblock` reuse the task row.

Reads reuse the same envelope:

- `brief`: `plan`, `task`, `next`, `criterion`, and `commit` rows plus a
  `metric` row for the active count.
- `audit`: `metric` rows (id is the name, title the value), `gap` rows, and
  `breach` rows in strict mode.
- `feed`: id is the event id, status the actor, title the detail, parent the
  `kind/action`, extra the timestamp.
- `info`: id is the key and title the value, including every count.
- `commits`: id is the full SHA, status `linked|stale`, title the subject,
  parent `kind:id`, extra the repo root.
- `repos`: id is the path, status `explicit|effective`, title the remote,
  parent `kind:id`, extra the recorded branch.
- `git status`: id is the path, status `clean|dirty|error`, title the branch,
  parent `kind:id` or `-`, extra head/ahead/behind/upstream/subject.
- `git scan`: id is the SHA, status the action, title the subject, parent the
  matched ref.
- `pr list|show`: id is the number, status the cached state, title the PR
  title, parent `kind:id`, extra the URL.
- `pr status`: id is the path, status `ready|error`, title the slug, parent
  `kind:id` or `-`, extra provider/auth/cache/remote.

Text fields never carry a tab or newline: separators become a
single space, so every record stays parseable with `line.split("\\t")`.

Enable with `--porcelain` (before or after the verb) or
`LAZYPLAN_PORCELAIN=1`. `--json` always wins when both are present, so the
full-fidelity escape hatch stays unambiguous.

Pure formatting only: this module never reads the store and never imports
Textual, so the CLI path stays fast and dependency-free.
"""

from __future__ import annotations

import os
import re
from typing import Any

ENV = "LAZYPLAN_PORCELAIN"
_TRUE = {"1", "true", "yes", "on"}
_SEPARATORS = re.compile(r"[\t\r\n]+")


def env_enabled(value: str | None = None) -> bool:
    """True when the value (or the environment switch) asks for porcelain."""
    raw = os.environ.get(ENV, "") if value is None else value
    return raw.strip().lower() in _TRUE


def enabled(args: Any) -> bool:
    """Porcelain is on unless JSON asked for full fidelity."""
    if getattr(args, "json", False):
        return False
    if getattr(args, "porcelain", False):
        return True
    return env_enabled()


def clean(value: Any) -> str:
    """Flatten tabs, carriage returns, and newlines so one record stays one line."""
    text = "" if value is None else str(value)
    return _SEPARATORS.sub(" ", text).strip()


def field(value: Any) -> str:
    """A non-empty row field; missing values use the documented dash."""
    return clean(value) or "-"


def row(
    kind: Any,
    obj_id: Any,
    status: Any,
    title: Any,
    parent: Any = "-",
    extra: Any = "-",
) -> str:
    """Render one porcelain record in the documented six-column order."""
    return "\t".join(
        (
            field(kind),
            field(obj_id),
            field(status),
            field(title),
            field(parent),
            field(extra),
        )
    )


def plan_row(plan_id: Any, status: Any, title: Any, progress: Any = "-") -> str:
    """A plan row: no parent, task progress in extra."""
    return row("plan", plan_id, status, title, "-", progress)


def milestone_row(
    milestone_id: Any, status: Any, title: Any, plan_id: Any, progress: Any = "-"
) -> str:
    """A milestone row: the owning plan in parent, task progress in extra."""
    return row("milestone", milestone_id, status, title, f"plan:{field(plan_id)}", progress)


def task_row(task_id: Any, status: Any, title: Any, milestone_id: Any, extra: Any = "-") -> str:
    """A task row: the owning milestone in parent, blocked marker in extra."""
    return row("task", task_id, status, title, f"milestone:{field(milestone_id)}", extra)


def text_row(kind: Any, text: Any) -> str:
    """A labeled text row such as `why`, `what`, or `desc`."""
    return row(kind, "-", "-", text)


def claim_row(task_id: Any, actor: Any, title: Any, expires_at: float | int | None = None) -> str:
    """A lease record: id is the task, status the actor, extra the expiry epoch."""
    return row("claim", task_id, actor, title, f"task:{field(task_id)}", expires_at or "-")


def comment_row(
    comment_id: Any,
    actor: Any,
    text: Any,
    parent_kind: Any,
    parent_id: Any,
    ts: Any,
    resolved: bool,
) -> str:
    """A review comment: status is resolved|open."""
    return row(
        "comment",
        comment_id,
        "resolved" if resolved else "open",
        text,
        f"{field(parent_kind)}:{field(parent_id)}",
        int(ts),
    )


def link_row(criterion_id: Any, status: Any, task_id: Any, title: Any) -> str:
    """A criterion-task proof relation."""
    return row(
        "link",
        criterion_id,
        status,
        title,
        f"criterion:{field(criterion_id)}",
        f"task:{field(task_id)}",
    )


def note_row(note_id: Any, actor: Any, text: Any, parent_kind: Any, parent_id: Any, ts: Any) -> str:
    """A handoff note: status is the actor, parent is the owning row."""
    return row("note", note_id, actor, text, f"{field(parent_kind)}:{field(parent_id)}", int(ts))
