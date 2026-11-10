"""Canonical palette catalog behind the registry facade.

The registry re-exports every name here so ``palette.py`` and ``help.py`` stay
thin facades. Rows are ordered for the palette; the section list, glossary
verbs, and nouns are the single source for the palette, help screen, and CLI
help.
"""

from __future__ import annotations

from dataclasses import dataclass

CREATE = "Create"
EDIT = "Edit"
VIEW = "View"
APP = "App"
SECTIONS: tuple[str, ...] = (VIEW, APP, CREATE, EDIT)

# -- canonical glossary ---------------------------------------------------
VERBS: tuple[str, ...] = (
    "add",
    "edit",
    "move",
    "delete",
    "show",
    "list",
    "export",
    "help",
)
NOUNS: tuple[str, ...] = ("plan", "milestone", "task", "criterion")


@dataclass(frozen=True)
class Command:
    """One named action shared by the palette, keymap, and help."""

    id: str
    label: str
    section: str
    action_id: str = ""
    verb: str = ""
    nouns: tuple[str, ...] = ()
    key: str = ""
    help_key: str = ""
    context: str = "always"
    handler: str = ""
    aliases: tuple[str, ...] = ()
    help_group: str = ""
    help_hint: str = ""
    screens: tuple[str, ...] = ("tree",)
    in_palette: bool = True
    tui_only: bool = False

    @property
    def mode(self) -> str:
        """Observe for read-only sections; write for create and edit."""
        return "write" if self.section in (CREATE, EDIT) else "observe"


# fmt: off
COMMANDS: tuple[Command, ...] = (
    Command(id='create-plan', label='Create plan', section=CREATE, action_id='plan.create', verb='add', nouns=('plan',), help_key='n', handler='new_plan', aliases=('add plan', 'add-plan', 'create', 'new plan'), help_group='CHANGE', help_hint='new plan / milestone / task by context'),
    Command(id='create-milestone', label='Create milestone', section=CREATE, action_id='milestone.create', verb='add', nouns=('milestone',), context='plan', handler='new_milestone', aliases=('add milestone', 'add-milestone', 'new milestone'), help_group='CHANGE', help_hint='new milestone in the selected plan'),
    Command(id='create-task', label='Create task', section=CREATE, action_id='task.create', verb='add', nouns=('task',), context='milestone', handler='new_task', aliases=('add task', 'add-task', 'new task'), help_group='CHANGE', help_hint='new task in the selected milestone'),
    Command(id='add-criterion', label='Add criterion', section=CREATE, action_id='criterion.add', verb='add', nouns=('criterion',), key='a', context='selection', handler='add_criterion', aliases=('add criteria', 'add-criteria', 'new criterion'), help_group='CHANGE', help_hint='add a criterion to the selection'),
    Command(id='approve-plan', label='Approve plan scope', section=EDIT, action_id='plan.approve', context='plan', handler='approve_plan', aliases=('approve', 'approval', 'snapshot', 'sign off'), help_group='TRUST', help_hint='record the current plan as an approved revision', tui_only=True),
    Command(id='add-question', label='Add plan question', section=EDIT, action_id='question.add', context='plan', handler='add_question', aliases=('question', 'ambiguity', 'ask'), help_group='TRUST', help_hint='record a plan-level ambiguity', tui_only=True),
    Command(id='resolve-question', label='Resolve plan question', section=EDIT, action_id='question.resolve', context='plan', handler='resolve_question', aliases=('resolve question', 'answer'), help_group='TRUST', help_hint='close one open plan question by id', tui_only=True),
    Command(id='reopen-question', label='Reopen plan question', section=EDIT, action_id='question.reopen', context='plan', handler='reopen_question', aliases=('reopen question', 'reopen ambiguity'), help_group='TRUST', help_hint='reopen one resolved plan question by id', tui_only=True),
    Command(id='link-ref', label='Link external reference', section=EDIT, action_id='reference.link', context='plan', handler='link_ref', aliases=('link ref', 'reference', 'epic', 'issue'), help_group='TRUST', help_hint='attach a read-only external URL to the plan', tui_only=True),
    Command(id='unlink-ref', label='Unlink external reference', section=EDIT, action_id='reference.unlink', context='plan', handler='unlink_ref', aliases=('unlink ref', 'remove reference'), help_group='TRUST', help_hint='remove one reference by id or URL', tui_only=True),
    Command(id='claim-task', label='Claim task', section=EDIT, action_id='task.claim', context='selection', handler='claim_task', aliases=('claim', 'lease', 'take task'), help_group='TRUST', help_hint='claim the selected task and move it doing', tui_only=True),
    Command(id='block-task', label='Block task', section=EDIT, action_id='task.block', context='selection', handler='block_task', aliases=('block', 'waiting', 'park'), help_group='TRUST', help_hint='block a task with a reason', tui_only=True),
    Command(id='unblock-task', label='Unblock task', section=EDIT, action_id='task.unblock', context='selection', handler='unblock_task', aliases=('unblock', 'resume task'), help_group='TRUST', help_hint="clear a task's blocked flag", tui_only=True),
    Command(id='finish-task', label='Finish task', section=EDIT, action_id='task.finish', context='selection', handler='finish_task', aliases=('finish', 'close task', 'done with commits'), help_group='TRUST', help_hint='link commits and close the task through the finish gates', tui_only=True),
    Command(id='edit-selection', label='Edit selection', section=EDIT, action_id='row.edit', verb='edit', nouns=('plan', 'milestone', 'task'), key='e', context='selection', handler='edit_selection', aliases=('update', 'edit', 'rename'), help_group='CHANGE', help_hint='edit the selected row'),
    Command(id='move-todo', label='Move to todo', section=EDIT, action_id='task.move', verb='move', nouns=('plan', 'milestone', 'task'), context='selection', handler='move_todo', aliases=('mark todo', 'reopen'), help_group='CHANGE', help_hint='move the selection back to todo'),
    Command(id='move-doing', label='Move to doing', section=EDIT, action_id='task.move', verb='move', nouns=('plan', 'milestone', 'task'), help_key='s', context='selection', handler='move_doing', aliases=('cycle status', 'advance status', 'mark doing', 'start'), help_group='CHANGE', help_hint='advance status: todo → doing → done'),
    Command(id='move-done', label='Move to done', section=EDIT, action_id='task.move', verb='move', nouns=('plan', 'milestone', 'task'), context='selection', handler='move_done', aliases=('mark done', 'complete', 'finish'), help_group='CHANGE', help_hint='move the selection to done'),
    Command(id='release-claim', label='Release claim', section=EDIT, action_id='claim.release', context='selection', handler='release_claim', aliases=('release claim', 'clear claim'), help_group='CHANGE', help_hint='release your task lease', tui_only=True),
    Command(id='force-release-claim', label='Force release claim', section=EDIT, action_id='claim.force_release', context='selection', handler='force_release_claim', aliases=('force release claim', 'take over claim'), help_group='CHANGE', help_hint="release someone else's lease with a reason", tui_only=True),
    Command(id='delete-selection', label='Delete selection', section=EDIT, action_id='row.delete', verb='delete', nouns=('plan', 'milestone', 'task'), key='d', context='selection', handler='delete_selection', aliases=('delete', 'remove', 'delete with confirm'), help_group='CHANGE', help_hint='delete the selection after a confirm'),
    Command(id='git-capture', label='Link current commit', section=EDIT, action_id='commit.link', context='selection', handler='git_capture', aliases=('link commit', 'capture commit', 'attach commit'), help_group='CHANGE', help_hint='link the safe current HEAD to the selection', tui_only=True),
    Command(id='fold-one', label='Fold/unfold row', section=VIEW, action_id='view.fold', key='z', context='selection', handler='fold', aliases=('fold one', 'fold', 'unfold'), help_group='MOVE', help_hint='fold or unfold the selected row', tui_only=True),
    Command(id='fold-all', label='Fold/unfold all', section=VIEW, action_id='view.fold', key='Z', handler='fold_all', aliases=('fold all', 'unfold all'), help_group='MOVE', help_hint='fold or unfold every row', tui_only=True),
    Command(id='filter-text', label='Filter by text', section=VIEW, action_id='view.filter', verb='list', key='/', handler='filter_text', aliases=('filter by text', 'filter', 'search'), help_group='FIND', help_hint='filter the tree by text'),
    Command(id='refresh', label='Refresh', section=VIEW, action_id='view.refresh', key='r', handler='refresh', aliases=('reload',), help_group='FIND', help_hint='refresh the tree', tui_only=True),
    Command(id='git-status', label='Show git status', section=VIEW, action_id='git.status', context='selection', handler='git_status', aliases=('git', 'branch', 'dirty', 'checkout status'), help_group='FIND', help_hint='branch and dirty state for linked repos', tui_only=True),
    Command(id='git-refresh', label='Refresh commit links', section=VIEW, action_id='commit.refresh', context='selection', handler='git_refresh', aliases=('refresh commits', 'stale commits', 'refresh git'), help_group='FIND', help_hint='re-resolve commits and mark stale links', tui_only=True),
    Command(id='open-pr', label='Open pull request', section=VIEW, action_id='pull_request.open', context='selection', handler='open_pr', aliases=('open pr', 'pull request', 'github', 'browser'), help_group='FIND', help_hint='open the first linked PR in your browser', tui_only=True),
    Command(id='source-trail', label='Open source trail', section=VIEW, action_id='source.trail', key='g', context='selection', handler='source_trail', aliases=('source', 'git trail', 'where', 'provenance'), help_group='FIND', help_hint='repos, commits, files, and PRs for the selected row', tui_only=True),
    Command(id='criteria-hub', label='Open criteria hub', section=VIEW, action_id='view.criteria_hub', context='selection', handler='open_criteria_hub', aliases=('criteria hub', 'criteria', 'checklist'), help_group='TRUST', help_hint='select, add, edit, or delete criteria', screens=('tree', 'hub'), tui_only=True),
    Command(id='evidence-hub', label='Open evidence hub', section=VIEW, action_id='view.evidence_hub', context='plan', handler='open_evidence_hub', aliases=('evidence hub', 'proof', 'evidence'), help_group='TRUST', help_hint='browse proof rows for a criterion', screens=('tree', 'hub'), tui_only=True),
    Command(id='questions-hub', label='Open questions hub', section=VIEW, action_id='view.questions_hub', context='plan', handler='open_questions_hub', aliases=('questions hub', 'questions', 'ambiguities'), help_group='TRUST', help_hint='add, resolve, or reopen plan questions', screens=('tree', 'hub'), tui_only=True),
    Command(id='references-hub', label='Open references hub', section=VIEW, action_id='view.references_hub', context='plan', handler='open_references_hub', aliases=('references hub', 'references', 'links'), help_group='TRUST', help_hint='link, open, or remove external references', screens=('tree', 'hub'), tui_only=True),
    Command(id='claims-hub', label='Open claims hub', section=VIEW, action_id='view.claims_hub', context='selection', handler='open_claims_hub', aliases=('claims hub', 'claims', 'touchpoints', 'touch-points'), help_group='TRUST', help_hint='leases, expiry, renew, release, and touch-points', screens=('tree', 'hub'), tui_only=True),
    Command(id='sessions-hub', label='Open sessions hub', section=VIEW, action_id='view.sessions_hub', context='plan', handler='open_sessions_hub', aliases=('sessions hub', 'sessions', 'handoff'), help_group='TRUST', help_hint='start, end, and read sessions and handoffs', screens=('tree', 'hub'), tui_only=True),
    Command(id='comments-hub', label='Open comments and notes hub', section=VIEW, action_id='view.comments_hub', context='selection', handler='open_comments_hub', aliases=('comments hub', 'comments', 'notes'), help_group='TRUST', help_hint='add comments and notes, and resolve comments', screens=('tree', 'hub'), tui_only=True),
    Command(id='pull-requests-hub', label='Open pull request hub', section=VIEW, action_id='view.pull_requests_hub', context='selection', handler='open_pull_requests_hub', aliases=('pull request hub', 'pull requests', 'prs', 'github pulls'), help_group='TRUST', help_hint='browse cached pull requests and their checks', screens=('tree', 'hub'), tui_only=True),
    Command(id='refresh-prs', label='Refresh pull requests', section=EDIT, action_id='pull_request.refresh', context='selection', handler='refresh_prs', aliases=('refresh prs', 'fetch prs', 'github refresh'), help_group='CHANGE', help_hint='refresh cached pull requests from GitHub (network)', screens=('tree', 'hub'), tui_only=True),
    Command(id='link-pr', label='Link pull request', section=EDIT, action_id='pull_request.link', context='selection', handler='link_pr', aliases=('link pr', 'attach pr', 'add pull request'), help_group='CHANGE', help_hint='attach a GitHub pull request URL to the selection', screens=('tree', 'hub'), tui_only=True),
    Command(id='unlink-pr', label='Unlink pull request', section=EDIT, action_id='pull_request.unlink', context='selection', handler='unlink_pr', aliases=('unlink pr', 'detach pr', 'remove pull request'), help_group='CHANGE', help_hint='detach a cached pull request by number', screens=('tree', 'hub'), tui_only=True),
    Command(id='activity-hub', label='Open activity hub', section=VIEW, action_id='event.list', context='always', handler='open_activity_hub', aliases=('activity hub', 'activity', 'feed', 'events'), help_group='FIND', help_hint='recent feed rows with jump targets', screens=('any',), tui_only=True),
    Command(id='plan-diff', label='Show plan diff', section=VIEW, action_id='plan.diff', context='plan', handler='plan_diff', aliases=('diff', 'drift', 'revisions', 'scope changes'), help_group='FIND', help_hint='scope changes since the last approval', tui_only=True),
    Command(id='cycle-theme', label='Cycle theme', section=APP, action_id='theme.cycle', key='t', handler='cycle_theme', aliases=('theme', 'dark', 'light', 'void', 'mocha', 'latte', 'appearance'), help_group='APP', help_hint='cycle mocha / void / latte', screens=('any',), tui_only=True),
    Command(id='toggle-timeline', label='Show/hide timeline', section=APP, action_id='view.timeline', key='T', handler='toggle_timeline', aliases=('timeline', 'hide timeline', 'show timeline', 'gantt'), help_group='APP', help_hint='show or hide the timeline card', screens=('any',), tui_only=True),
    Command(id='command-palette', label='Command palette', section=APP, action_id='palette.open', key='c', handler='command_palette', aliases=('commands', 'palette'), help_group='APP', help_hint='open the command palette', screens=('any',), in_palette=False, tui_only=True),
    Command(id='export-plan', label='Export plan as Markdown…', section=APP, action_id='plan.export', verb='export', context='plan', handler='export_md', aliases=('export plan .md', 'export md', 'markdown'), help_group='APP', help_hint='choose a folder and filename for the Markdown export'),
    Command(id='update-lpui', label='Update lpui', section=APP, action_id='app.update', key='U', handler='update_prompt', aliases=('update', 'upgrade', 'new version'), help_group='APP', help_hint='download a newer release for the next launch', screens=('any',), tui_only=True),
    Command(id='help', label='Help', section=APP, action_id='app.help', verb='help', key='?', handler='help', aliases=('keys', 'keybindings'), help_group='APP', help_hint='this help', screens=('any',)),
    Command(id='quit', label='Quit', section=APP, action_id='app.quit', key='q', handler='quit', aliases=('exit',), help_group='APP', help_hint='quit the screen', screens=('any',), tui_only=True),
)
# fmt: on


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


def _match_rank(cmd: Command, query: str) -> int:
    """0 exact id/label/alias, 1 prefix, 2 substring anywhere."""
    if not query:
        return 0
    exact = [
        cmd.id.replace("-", " "),
        cmd.label.lower(),
        *(alias.lower() for alias in cmd.aliases),
    ]
    if query in exact:
        return 0
    if any(item.startswith(query) for item in exact):
        return 1
    return 2


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
    return _match_rank(cmd, query) < 2 or any(query in item.lower() for item in haystack if item)


def matching(query: str) -> list[tuple[str, list[Command]]]:
    """Palette sections for a query; exact aliases rank ahead of substrings."""
    q = query.strip().lower()
    sections: list[tuple[str, list[Command], int]] = []
    for section in SECTIONS:
        cmds = [
            cmd
            for cmd in COMMANDS
            if cmd.in_palette and cmd.section == section and _matches(cmd, q)
        ]
        if cmds:
            cmds.sort(key=lambda cmd: _match_rank(cmd, q))
            sections.append((section, cmds, min(_match_rank(cmd, q) for cmd in cmds)))
    sections.sort(key=lambda item: item[2])
    return [(section, cmds) for section, cmds, _rank in sections]


@dataclass(frozen=True)
class Context:
    """What the current screen can act on, independent of Textual."""

    screen: str = "tree"
    selected_kind: str | None = None
    has_plan: bool = False
    has_milestone: bool = False
    on_root: bool = False


#: Row kinds where a command is unavailable even though it has a selection.
DISABLED_FOR: dict[str, tuple[tuple[str, str], ...]] = {
    "fold-one": (("task", "Nothing to fold"),),
}


def palette_context(ctx: Context) -> dict[str, str | None]:
    """Palette availability for one context: id -> reason or None.

    Every rule lives here so the app and the palette cannot drift apart: the
    screen gate runs first, then the declaration on the command, then the
    row-kind exceptions.
    """
    reasons: dict[str, str | None] = {}
    for cmd in COMMANDS:
        reason: str | None = None
        if cmd.screens != ("any",) and ctx.screen not in cmd.screens:
            reason = "Only available on the tree"
        elif cmd.context == "selection" and ctx.selected_kind is None:
            reason = "Select a row first"
        elif cmd.context == "plan" and not ctx.has_plan:
            reason = "Select a plan first"
        elif cmd.context == "milestone" and not ctx.has_milestone:
            reason = "Select a milestone first"
        else:
            for kind, why in DISABLED_FOR.get(cmd.id, ()):
                if ctx.selected_kind == kind:
                    reason = why
                    break
        reasons[cmd.id] = reason
    return reasons


PALETTE_COMMANDS = tuple((cmd.id, cmd.label) for cmd in palette_commands())
PALETTE_SECTIONS = palette_sections()
