"""Canonical commands, key hints, and help text for every surface.

The TUI palette, the key map, the help screen, and `lpui help` all render
from this module. It imports the standard library only, so the CLI and the
stdlib test run can use it without Textual installed.

Rule: add a command here first. The palette, keymap, and help follow.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- sections (palette order) ---------------------------------------------
CREATE = "Create"
EDIT = "Edit"
VIEW = "View"
APP = "App"
SECTIONS: tuple[str, ...] = (CREATE, EDIT, VIEW, APP)

# -- canonical glossary ---------------------------------------------------
VERBS: tuple[str, ...] = (
    "add",
    "edit",
    "move",
    "tick",
    "untick",
    "delete",
    "show",
    "list",
    "export",
    "help",
)
NOUNS: tuple[str, ...] = ("plan", "milestone", "task", "criterion")

#: Legacy CLI verbs that must keep working as aliases for canonical work.
#: The parser is the source of truth; this table drives the parity tests
#: until the noun-first groups land and then keeps the aliases honest.
LEGACY_COMMANDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("plan", "add"): ("add-plan",),
    ("milestone", "add"): ("add-milestone",),
    ("task", "add"): ("add-task",),
    ("criterion", "add"): ("add-criteria",),
    ("plan", "edit"): ("update",),
    ("milestone", "edit"): ("update",),
    ("task", "edit"): ("update",),
    ("plan", "move"): ("status",),
    ("milestone", "move"): ("status",),
    ("task", "move"): ("status",),
    ("criterion", "tick"): ("check",),
    ("criterion", "untick"): ("uncheck",),
    ("plan", "delete"): ("delete",),
    ("milestone", "delete"): ("delete",),
    ("task", "delete"): ("delete",),
    ("criterion", "delete"): ("delete-criteria",),
    ("plan", "show"): ("show",),
    ("milestone", "show"): ("show",),
    ("task", "show"): ("show",),
    ("", "list"): ("list",),
    ("", "export"): ("export",),
    ("", "help"): ("help",),
}


@dataclass(frozen=True)
class Command:
    """One named action shared by the palette, keymap, and help."""

    id: str
    label: str
    section: str
    verb: str = ""
    nouns: tuple[str, ...] = ()
    key: str = ""
    help_key: str = ""
    context: str = "always"
    handler: str = ""
    aliases: tuple[str, ...] = ()
    help_group: str = ""
    help_hint: str = ""
    in_palette: bool = True
    tui_only: bool = False


COMMANDS: tuple[Command, ...] = (
    # -- create ----------------------------------------------------------
    Command(
        id="create-plan",
        label="Create plan",
        section=CREATE,
        verb="add",
        nouns=("plan",),
        context="always",
        handler="new_plan",
        aliases=("add plan", "add-plan", "create", "new plan"),
        help_group="CHANGE",
        help_hint="new plan / milestone / task by context",
        help_key="n",
    ),
    Command(
        id="create-milestone",
        label="Create milestone",
        section=CREATE,
        verb="add",
        nouns=("milestone",),
        context="plan",
        handler="new_milestone",
        aliases=("add milestone", "add-milestone", "new milestone"),
        help_group="CHANGE",
        help_hint="new milestone in the selected plan",
    ),
    Command(
        id="create-task",
        label="Create task",
        section=CREATE,
        verb="add",
        nouns=("task",),
        context="milestone",
        handler="new_task",
        aliases=("add task", "add-task", "new task"),
        help_group="CHANGE",
        help_hint="new task in the selected milestone",
    ),
    Command(
        id="add-criterion",
        label="Add criterion",
        section=CREATE,
        verb="add",
        nouns=("criterion",),
        key="a",
        context="selection",
        handler="add_criterion",
        aliases=("add criteria", "add-criteria", "new criterion"),
        help_group="CHANGE",
        help_hint="add a criterion to the selection",
    ),
    # -- edit ------------------------------------------------------------
    Command(
        id="edit-selection",
        label="Edit selection",
        section=EDIT,
        verb="edit",
        nouns=("plan", "milestone", "task"),
        key="e",
        context="selection",
        handler="edit_selection",
        aliases=("update", "edit", "rename"),
        help_group="CHANGE",
        help_hint="edit the selected row",
    ),
    Command(
        id="move-todo",
        label="Move to todo",
        section=EDIT,
        verb="move",
        nouns=("plan", "milestone", "task"),
        context="selection",
        handler="move_todo",
        aliases=("mark todo", "reopen"),
        help_group="CHANGE",
        help_hint="move the selection back to todo",
    ),
    Command(
        id="move-doing",
        label="Move to doing",
        section=EDIT,
        verb="move",
        nouns=("plan", "milestone", "task"),
        context="selection",
        handler="move_doing",
        aliases=("cycle status", "advance status", "mark doing", "start"),
        help_group="CHANGE",
        help_hint="advance status: todo → doing → done",
        help_key="s",
    ),
    Command(
        id="move-done",
        label="Move to done",
        section=EDIT,
        verb="move",
        nouns=("plan", "milestone", "task"),
        context="selection",
        handler="move_done",
        aliases=("mark done", "complete", "finish"),
        help_group="CHANGE",
        help_hint="move the selection to done",
    ),
    Command(
        id="toggle-mark",
        label="Mark/unmark row",
        section=EDIT,
        key="space",
        context="selection",
        handler="toggle_mark",
        aliases=("mark", "unmark", "select row"),
        help_group="MOVE",
        help_hint="mark the selected row for bulk actions",
        tui_only=True,
    ),
    Command(
        id="clear-marks",
        label="Clear marks",
        section=EDIT,
        context="always",
        handler="clear_marks",
        aliases=("clear marks", "unmark all"),
        help_group="MOVE",
        help_hint="clear every marked row",
        tui_only=True,
    ),
    Command(
        id="release-claim",
        label="Release claim",
        section=EDIT,
        context="selection",
        handler="release_claim",
        aliases=("release claim", "clear claim"),
        help_group="CHANGE",
        help_hint="release your task lease",
        tui_only=True,
    ),
    Command(
        id="force-release-claim",
        label="Force release claim",
        section=EDIT,
        context="selection",
        handler="force_release_claim",
        aliases=("force release claim", "take over claim"),
        help_group="CHANGE",
        help_hint="release someone else's lease with a reason",
        tui_only=True,
    ),
    Command(
        id="tick-criterion",
        label="Tick next criterion",
        section=EDIT,
        verb="tick",
        nouns=("criterion",),
        key="x",
        context="selection",
        handler="tick_criterion",
        aliases=("tick criteria", "check", "tick"),
        help_group="CHANGE",
        help_hint="tick the next open criterion",
    ),
    Command(
        id="untick-criterion",
        label="Reopen last criterion",
        section=EDIT,
        verb="untick",
        nouns=("criterion",),
        context="selection",
        handler="untick_criterion",
        aliases=("uncheck", "reopen criterion"),
        help_group="CHANGE",
        help_hint="reopen the last ticked criterion",
    ),
    Command(
        id="delete-selection",
        label="Delete selection",
        section=EDIT,
        verb="delete",
        nouns=("plan", "milestone", "task"),
        key="d",
        context="selection",
        handler="delete_selection",
        aliases=("delete", "remove", "delete with confirm"),
        help_group="CHANGE",
        help_hint="delete the selection after a confirm",
    ),
    Command(
        id="git-capture",
        label="Link current commit",
        section=EDIT,
        context="selection",
        handler="git_capture",
        aliases=("link commit", "capture commit", "attach commit"),
        help_group="CHANGE",
        help_hint="link the safe current HEAD to the selection",
        tui_only=True,
    ),
    Command(
        id="bulk-doing",
        label="Bulk move to doing",
        section=EDIT,
        context="always",
        handler="bulk_doing",
        aliases=("bulk doing", "mark doing"),
        help_group="CHANGE",
        help_hint="move marked tasks to doing",
        tui_only=True,
    ),
    Command(
        id="bulk-done",
        label="Bulk move to done",
        section=EDIT,
        context="always",
        handler="bulk_done",
        aliases=("bulk done", "mark done"),
        help_group="CHANGE",
        help_hint="move marked tasks to done",
        tui_only=True,
    ),
    Command(
        id="bulk-block",
        label="Bulk block tasks",
        section=EDIT,
        context="always",
        handler="bulk_block",
        aliases=("bulk block", "block marked"),
        help_group="CHANGE",
        help_hint="block marked tasks with a reason",
        tui_only=True,
    ),
    Command(
        id="bulk-release",
        label="Bulk release claims",
        section=EDIT,
        context="always",
        handler="bulk_release",
        aliases=("bulk release", "release marked"),
        help_group="CHANGE",
        help_hint="release claims on marked tasks",
        tui_only=True,
    ),
    Command(
        id="undo-bulk",
        label="Undo bulk change",
        section=EDIT,
        context="always",
        handler="undo_bulk",
        aliases=("undo", "undo bulk"),
        help_group="CHANGE",
        help_hint="restore the last bulk status/block change",
        tui_only=True,
    ),
    # -- view ------------------------------------------------------------
    Command(
        id="open-detail",
        label="Open detail",
        section=VIEW,
        verb="show",
        nouns=("plan", "milestone", "task"),
        key="enter",
        context="selection",
        handler="open_detail",
        aliases=("show", "detail", "open"),
        help_group="MOVE",
        help_hint="open detail (or double-click)",
    ),
    Command(
        id="fold-one",
        label="Fold/unfold row",
        section=VIEW,
        key="z",
        context="selection",
        handler="fold",
        aliases=("fold one", "fold", "unfold"),
        help_group="MOVE",
        help_hint="fold or unfold the selected row",
        tui_only=True,
    ),
    Command(
        id="fold-all",
        label="Fold/unfold all",
        section=VIEW,
        key="Z",
        context="always",
        handler="fold_all",
        aliases=("fold all", "unfold all"),
        help_group="MOVE",
        help_hint="fold or unfold every row",
        tui_only=True,
    ),
    Command(
        id="filter-text",
        label="Filter by text",
        section=VIEW,
        verb="list",
        key="/",
        context="always",
        handler="filter_text",
        aliases=("filter by text", "filter", "search"),
        help_group="FIND",
        help_hint="filter the tree by text",
    ),
    Command(
        id="filter-status",
        label="Filter by status",
        section=VIEW,
        verb="list",
        key="f",
        context="always",
        handler="filter_status",
        aliases=("cycle status filter", "status filter"),
        help_group="FIND",
        help_hint="change the status filter",
    ),
    Command(
        id="filter-source",
        label="Filter by source",
        section=VIEW,
        verb="list",
        key="F",
        context="always",
        handler="filter_source",
        aliases=("cycle source filter", "source filter", "unlinked", "stale"),
        help_group="FIND",
        help_hint="cycle all / linked / PR / stale / unlinked / claims / blocked / attention",
    ),
    Command(
        id="toggle-done",
        label="Show/hide completed plans",
        section=VIEW,
        verb="list",
        key="A",
        context="always",
        handler="toggle_show_all",
        aliases=("show all", "show all / capped", "all plans", "show completed"),
        help_group="FIND",
        help_hint="show every plan, or just recent ones",
    ),
    Command(
        id="refresh",
        label="Refresh",
        section=VIEW,
        key="r",
        context="always",
        handler="refresh",
        aliases=("reload",),
        help_group="FIND",
        help_hint="refresh the tree",
        tui_only=True,
    ),
    Command(
        id="git-status",
        label="Show git status",
        section=VIEW,
        context="selection",
        handler="git_status",
        aliases=("git", "branch", "dirty", "checkout status"),
        help_group="FIND",
        help_hint="branch and dirty state for linked repos",
        tui_only=True,
    ),
    Command(
        id="git-refresh",
        label="Refresh commit links",
        section=VIEW,
        context="selection",
        handler="git_refresh",
        aliases=("refresh commits", "stale commits", "refresh git"),
        help_group="FIND",
        help_hint="re-resolve commits and mark stale links",
        tui_only=True,
    ),
    Command(
        id="open-pr",
        label="Open pull request",
        section=VIEW,
        context="selection",
        handler="open_pr",
        aliases=("open pr", "pull request", "github", "browser"),
        help_group="FIND",
        help_hint="open the first linked PR in your browser",
        tui_only=True,
    ),
    Command(
        id="source-trail",
        label="Open source trail",
        section=VIEW,
        context="selection",
        key="g",
        handler="source_trail",
        aliases=("source", "git trail", "where", "provenance"),
        help_group="FIND",
        help_hint="repos, commits, files, and PRs for the selected row",
        tui_only=True,
    ),
    # -- app -------------------------------------------------------------
    Command(
        id="command-palette",
        label="Command palette",
        section=APP,
        key="c",
        context="always",
        handler="command_palette",
        aliases=("commands", "palette"),
        help_group="APP",
        help_hint="open the command palette",
        in_palette=False,
        tui_only=True,
    ),
    Command(
        id="export-plan",
        label="Export plan as Markdown",
        section=APP,
        verb="export",
        context="selection",
        handler="export_md",
        aliases=("export plan .md", "export md", "markdown"),
        help_group="APP",
        help_hint="export the selected plan to Markdown",
    ),
    Command(
        id="help",
        label="Help",
        section=APP,
        verb="help",
        key="?",
        context="always",
        handler="help",
        aliases=("keys", "keybindings"),
        help_group="APP",
        help_hint="this help",
    ),
    Command(
        id="quit",
        label="Quit",
        section=APP,
        key="q",
        context="always",
        handler="quit",
        aliases=("exit",),
        help_group="APP",
        help_hint="quit the screen",
        tui_only=True,
    ),
)


#: Navigation rows that are not palette commands.
def by_id(command_id: str) -> Command | None:
    """Look up one command by its stable id."""
    for cmd in COMMANDS:
        if cmd.id == command_id:
            return cmd
    return None


def palette_commands() -> tuple[Command, ...]:
    """Commands shown in the modal palette, in registry order."""
    return tuple(cmd for cmd in COMMANDS if cmd.in_palette)


def palette_sections() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Palette section headers and their command ids (single source)."""
    out: list[tuple[str, tuple[str, ...]]] = []
    for section in SECTIONS:
        ids = tuple(cmd.id for cmd in COMMANDS if cmd.in_palette and cmd.section == section)
        if ids:
            out.append((section, ids))
    return tuple(out)


def _matches(cmd: Command, query: str) -> bool:
    if not query:
        return True
    haystack = [
        cmd.id.replace("-", " "),
        cmd.label.lower(),
        cmd.help_hint.lower(),
        cmd.verb,
        *cmd.nouns,
        *cmd.aliases,
    ]
    return any(query in item.lower() for item in haystack if item)


def matching(query: str) -> list[tuple[str, list[Command]]]:
    """Palette sections for a query; section headers never match."""
    q = query.strip().lower()
    out: list[tuple[str, list[Command]]] = []
    for section in SECTIONS:
        cmds = [
            cmd
            for cmd in COMMANDS
            if cmd.in_palette and cmd.section == section and _matches(cmd, q)
        ]
        if cmds:
            out.append((section, cmds))
    return out


PALETTE_COMMANDS = tuple((cmd.id, cmd.label) for cmd in palette_commands())
PALETTE_SECTIONS = palette_sections()
