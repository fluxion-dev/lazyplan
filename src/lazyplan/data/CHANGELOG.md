# Changelog

Notable user-facing changes to lazyplan (`lpui`). Releases before 0.26.0 are
documented on the [GitHub releases page](https://github.com/fluxion-dev/lazyplan/releases).

## Unreleased

### Changed

- **Plans run in their own worktree.** A new plan is isolation-required:
  `plan worktree --print` emits one setup command per linked repo, `add` and
  `remove` register the real checkouts, and plan start, session start, next,
  and claim refuse the shared checkout unless `--force --reason` records an
  override. A done move refuses a dirty worktree and prints removal commands;
  `doctor` and `plan worktree list --stale` report drift without deleting
  anything. Plans created before the flag stay grandfathered.

## v0.42.0 — 2026-11-13

### Fixed

- **Source trails reach symlinked checkouts.** A commit recorded through a
  symlinked path now groups with its resolved checkout, so macOS checkouts and
  other symlinked repos show their commits instead of an empty repo row.

### Changed

- **The overview is a header list.** A plan lists its milestones and a
  milestone lists its tasks, each as one line with its status, id, and title.
  Task descriptions no longer repeat inline, so a milestone with detailed tasks
  stays scannable; select the task to read its details. The plan overview's
  `NEXT` shortcut list is gone.
- **The source trail explains the change.** Expanding a commit now shows each
  file's status and line counts. Diffs use tinted rows, aligned old/new
  gutters, folded context, changed-word emphasis, syntax colors, and a
  side-by-side toggle. `n` / `p` walk the files and `ctrl+d` / `ctrl+u` page a
  long diff. **Show plan diff** now opens a dedicated screen grouped by kind
  with before/after text and the reason for each change.

## v0.41.1 — 2026-11-12

### Fixed

- **Unrelated repositories commit freely again.** With strict hooks and the
  shared home database, an agent's first commit in any repository was denied,
  because the session row a hook opens counted as planned work. Only a session
  you started, or one attached to a plan, now marks a checkout as managed.
- **The commit gate reads the command.** Searching for or echoing the words
  `git commit` is no longer treated as a commit, and `git -C repo commit` is.
- **Hooks no longer hang on Windows.** When a host kept stdin open, the first
  git call a hook made never returned. The hook now reads only what the host
  has already written.
- **Agents see the post-tool reminder.** Claude Code, Codex, and Gemini get the
  commit-link and touched-path reminders as context for the agent instead of a
  warning only you see, a repository with nothing in progress and edits outside
  the repository stay quiet, and Claude Code's absolute Windows paths now match
  a task's touch-points.
- **Stop stays quiet.** The end of each agent turn no longer prints a reminder
  to end the session, and a blocked stop no longer asks the agent to end a
  session its host is still running.
- **Claude Code hooks have time to finish.** Managed entries wait at most 30
  seconds, and session end gets 10 seconds instead of Claude Code's 1.5.
- **Upgrades keep advisory hooks advisory.** Refreshing hooks after an upgrade
  no longer switches them back to strict.
- **OpenCode 1.x loads the plugin.** The released OpenCode rejected the plugin,
  which only spoke the 2.x API; it now loads on both.
- **Windows updates apply offline.** A downloaded pipx update no longer needs
  the package index to install.
- **Windows updates work for pipx installs built with uv.** pipx picks uv
  whenever it is on PATH, and those venvs have no pip, so `lpui upgrade` failed
  with `No module named pip`. The update now installs with `uv pip`, and a
  failed install always records `install failed` with the tool's output.
- **The MCP server reports its version** instead of `0`.
- **Release notes show v0.41.0 again.** The published section had no date, so
  `lpui notes` skipped it; the heading now carries its release date.

### Changed

- **Compaction keeps the plan.** Claude Code's compaction summary is asked to
  keep the active plan and task ids.
- **Hooks are faster.** A hook asks git for the checkout once instead of up to
  three times, which saves about a fifth of every hook and a third of Stop on
  Windows, and a hook outside any repository does not start git at all.

## v0.41.0 — 2026-11-12

### Added

- **Maintenance is one noun-first surface.** `lpui maint report` shows bytes
  and row counts per table with a reclaimable estimate; `maint archive`,
  `maint trim`, and `maint vacuum` preview by default and write only with
  `--apply`; `maint restore --plan` or `--session` returns an archived row.
  `maint report --days` sets the estimate window and separates used bytes from
  the file size. Every apply starts with a verified
  `lazyplan.db.bak-<timestamp>` snapshot and only derived link rows and old
  events are trimmed, keeping the newest plan status event per plan; plan text,
  criteria, evidence, notes, and comments are never trimmed. The TUI `m` hub shows the same candidate counts,
  and MCP exposes a read-only report plus apply-gated write tools.

### Changed

- **`--archived` is the archive switch; `--finished` keeps the old filter.**
  `lpui list --archived only` shows archived plans, `--archived all` shows
  both, and the default hides them. `--finished` still shows plans marked done
  longer than a day. Archived plans and sessions leave list, tree, brief, next,
  ready, stats, audit, trace, who, claims, and the agents panel, and
  `lpui maint restore --plan` or `--session` brings them back.

## v0.40.3 — 2026-11-11

### Changed

- **Task rows read like milestone rows.** A task row shows only the status
  glyph, `T<id>`, the title, and `!` when it needs attention, so the title keeps
  the width once spent on claim and blocked stats. A blocked task marks its own
  row and still marks its milestone and plan. Blocked detail and the claim
  holder stay in the task overview and coordination hubs.
- **The agents card reads like a live process list.** Each row shows the actor,
  a four-character agent id, the plan id and short title, the branch, the age,
  and a glyph: an animated frame while working, `◆` when awaiting, and `◌` when
  stale or idle. Plan and branch truncate with an ellipsis instead of wrapping.
- **Dead sessions leave sooner.** A row reads stale after two minutes, a
  working row is auto-closed after ten minutes, an awaiting row after thirty,
  and the background reap runs every minute.

## v0.40.2 — 2026-11-11

### Fixed

- **Your tree folds stay put.** Writes, new rows, reorders, and plans moving
  between plan queue and plan review no longer open or close branches, new rows
  start collapsed, and selecting a row inside a closed branch keeps it closed.
  A text filter reveals hits and then restores exactly the branches that were
  open before it.

## v0.40.1 — 2026-11-11

### Fixed

- **Agent rows name their plan and branch.** Every session records the
  checkout's branch and the plan its work belongs to, refreshes both on each
  heartbeat, and the agents card, sessions hub, and `lpui session` show the plan
  title, task, and branch instead of `no plan` or `PNone`.
- **Overview headings breathe.** Every heading in the overview now has one
  blank line above and below, including section bars and headings inside why,
  what, and details prose.

### Changed

- **Read-only agents card.** Clicking the agents card no longer opens the
  sessions hub or takes keyboard focus. Open the sessions hub from the command
  palette; the usage guide and packaged skill no longer mention a stale `v`
  shortcut.

## v0.40.0 — 2026-11-11

### Changed

- **Full acceptance criteria in the overview.** Selecting a plan now lists every
  acceptance criterion, open first, with its id, done state, and proof chip. No
  criterion is capped or hidden; milestone and task previews keep their short
  open list.

## v0.39.0 — 2026-11-11

### Added

- **Markdown overview.** The overview body is a native Markdown document:
  why, what, and details render lists, quotes, code fences, tables, and links,
  section headings become full-width bars, and only http/https links open.
- **Every agent session has its own row.** Each top-level host session now has
  its own row with its own phase and heartbeat, the OpenCode plugin passes the
  session id on every event, and the agents card, sessions hub, and
  `lpui session list` show every open session with a short host id. Child
  subagent sessions stay with their parent.

### Changed

- **Room to write.** Plan, milestone, and task create/edit dialogs use most of
  the screen, multiline editors grow to fill the form, and criterion and
  reference forms use the same scale. One-line prompts and small dialogs stay
  compact, with a compact fallback on small terminals.

### Fixed

- **The plan tree stays still while an agent works.** Session heartbeats refresh
  only the agents pane, real edits update affected rows in place, and the
  cursor, scroll, focus, preview, and spinner hold their position. The database
  poll runs on a worker and coalesces a burst of edits.

## v0.38.0 — 2026-11-11

### Added

- **Release notes after upgrades and on demand.** The installed package now
  carries the changelog. `lpui notes` prints the section for the installed
  version, `--all` prints every bundled release, `--since VERSION` prints a
  range, and `--json` returns versions, dates, and bodies. A successful
  `lpui upgrade` prints the notes for the versions it skipped, and the TUI
  opens the same notes once after an upgrade; `W` or the palette's Release
  notes command reopens them. A missing or corrupt seen-version marker counts
  as a first install and stays quiet.

### Changed

- **One work column.** The screen stacks plan queue, agents, plan review, and
  git in the left column and leaves the right column to the overview. Below 100
  columns the overview column hides and the four cards keep their order.

### Fixed

- **Hooks finish and sessions stay honest.** `lpui hook` bounds its stdin read
  instead of waiting for a pipe the host leaves open; the generated OpenCode
  plugin closes the child stdin, logs a failed hook once, and maps the V2
  lifecycle events. Host sessions and worktrees bind to one project row, tagged
  writes refresh the heartbeat, 15 minutes without progress reads `stale`, and
  two hours auto-closes the row. `lpui hook --check` and `lpui doctor` report
  hook readiness without writing.

## v0.37.0 — 2026-11-10

### Added

- **Strict lifecycle hooks.** `lpui setup --hooks` now installs strict hooks by
  default across OpenCode, Claude Code, Gemini CLI, Codex, and Cursor. Strict
  mode denies a `git commit` when a managed checkout has no doing task, blocks
  one stop per turn when commits are unlinked, injects the active plan on every
  prompt, nudges on task edits, and closes the session with a handoff. Use
  `--hooks advisory` for reminders only or `--no-hooks` to remove them;
  `LAZYPLAN_HOOKS=advisory` downgrades at runtime and `LAZYPLAN_NO_HOOKS=1`
  silences every hook. OpenCode denies commits through its permission hook but
  has no stop-block surface.
- **Live agent sessions.** Lifecycle hooks keep the checkout's session state
  current: a turn marks it working, a stop marks it awaiting, and the agents
  pane shows working, awaiting, and idle rows with awaiting first. Sessions
  idle for 12 hours close automatically with an auto-closed summary.

### Changed

- **Screen refresh.** The plan tree now splits queued and finished plans into
  stacked panels. On narrow terminals the preview hides and the cards stack.
  Rows show progress and one attention marker instead of commit
  and pull-request counts. Plan, milestone, and task overviews share one
  attention line and structured sections, hubs share one action footer, dialogs
  use a compact field and button scale, the palette moves with arrow keys, the
  source diff carries per-file counts, and the setup wizard uses the product
  palette.
- **Criterion completion.** `criterion edit --id C --done` (or `--open`) sets
  completion; `criterion prove` records evidence only.
- **Pane empty states.** The plans, preview, git, and agents panes share one
  empty-state treatment: a bold capitalized title and a dim next step.
- **Architecture seams.** Presentation constructs `Store` only in composition
  roots; store and services use injected path and layer adapters; parser groups
  and MCP metadata derive from the action registry; the largest modules split
  into focused files.
- **Overview replaces detail.** The separate detail page is gone. The preview
  pane is now the overview: a plan lists its milestones and descriptions, a
  milestone lists its tasks, and a task shows its details, criteria, proof, and
  notes. `e` edits the selected row in a modal form. The agents card now sits
  under the plan tree.

### Removed

- **ACP agent integration.** The `W` agent workbench, the `lpui agent` commands,
  the ACP transport, staged proposal review, and work sessions are gone. Plans,
  MCP, hooks, and the plan tree remain the agent paths.
- **Criterion tick.** `lpui criterion tick|untick`, the legacy `check|uncheck`
  aliases, the TUI `x` tick key, and the MCP `criterion_tick|untick` tools are
  gone.
- **Manual override mode and override feed.** The screen writes directly
  again; `O`, the banner, override audit events, `lpui feed --overrides`, the
  activity-hub override filter, and the MCP `overrides` flag are gone.
  Historical override rows remain in the normal feed.
- **Plan mode, bulk editing, and the TUI prove screen.** The `f` mode switch,
  space marks, bulk palette commands, and the prove form are gone. Criteria,
  evidence, and source stay readable in their hubs; `lpui criterion prove` and
  the MCP proof tool remain the write paths.
- **Legacy CLI verbs.** `add-plan`, `add-milestone`, `add-task`, `add-criteria`,
  `criteria`, `delete-criteria`, `update`, `status`, `delete`, and `show` are
  gone. Use the noun-first groups (`lpui plan add`, `lpui task edit`,
  `lpui criterion delete`, and so on). The deprecation guard now reports no
  remaining aliases.

## v0.36.0 — 2026-11-09

### Added

- **Agent workbench.** Press `W` to prompt an ACP agent beside the plan. The
  default is OpenCode (`opencode acp`); `lpui agent list`, `lpui agent add`, and
  `lpui agent remove` manage other commands. The screen streams assistant text,
  tool cards, plans, and usage, and asks for permission before a tool runs.
- **Proposal review.** Agents stage plan, milestone, task, and criterion changes
  as proposals. `ctrl+p` opens the human review screen; applying a proposal uses
  the normal plan-apply path.
- **Work sessions.** On a task detail, `W` claims the task, opens a lazyplan
  session, and prefills a work prompt. `ctrl+f` finishes with a summary and
  handoff behind the existing evidence, pull-request, and check gates.

### Changed

- **Cinematic site.** Rebuilt the landing page around the shared plan, the
  planner/executor loop, and proof, with a new hero composite, a feature matrix
  covering the major surfaces, and eight curated screenshots.

## v0.35.0 — 2026-11-08

The screen becomes a control room for the loop: large journals open faster,
navigation and hubs share one model, and the shell starts on the work instead
of the chart. Upgrades also review newly shipped agent integrations before they
land.

### Added

- **Control room.** A two-line health and needs strip summarizes readiness,
  approval drift, open questions, blocked work, claims, evidence, and touch
  overlaps. An agents pane shows active sessions, branches, ages, and the
  selected plan's last handoff.
- **Selectable hubs.** Criteria, evidence, questions, and references; claims,
  touch-points, sessions, comments, and notes; and the source trail, cached pull
  requests, and activity feed are all keyboard-selectable screens instead of
  read-only text.
- **Navigation history.** `[` and `]` move back and forward across screens and
  restore the exact prior selection, with breadcrumbs on every screen.
- **Lazy plan tree.** Collapsed plans and milestones no longer materialize child
  rows. Both mode paints the plan list immediately and loads a branch only when
  it opens, so large journals no longer stall on launch.
- **Manual override mode.** The screen is read-only by default. `O` arms
  writes behind a visible banner and nav subtitle; every write records a
  `tui/override` event, and risky writes ask for a reason.
- **Trust actions in the palette.** Approve a plan and show its diff, prove a
  criterion, add, resolve, or reopen questions, link or unlink references,
  claim, block, unblock, and finish a task without leaving the screen. The
  palette and help group actions by Observe and Override intent, with a TRUST
  group for approval and evidence.
- **Override feed.** `lpui feed --overrides` lists only the manual changes made
  from the screen.
- **New-integration review.** After a version change, one prompt lists the
  pending skills and hook hosts with install-all, not-now, and never choices.
  The answer is remembered per item with its fingerprint and version.
- **Doctor pending report.** `lpui doctor` names every pending integration and
  exits non-zero until it is answered.
- **Criterion and comment edits.** The criteria and comments hubs edit in
  place; `criterion edit`, `comment edit`, and the collaboration and provenance
  MCP tools match the screen.

### Changed

- **Plan modes.** The plans tree cycles Active, Finished, and Both with `f`.
  The old status and source filter cycles, `F`, `A`, and the five-plan cap are
  gone; attention data stays in the control strip.
- **Timeline on demand.** The timeline card starts hidden so the tree and
  preview get the full shell. Press `T` or run the palette's show or hide
  timeline command to open it for the session; below 100 columns it stays
  hidden.
- **One access-path registry.** Palette IDs, CLI paths, and MCP tools now map
  from one canonical action table, with a parity gate that rejects an
  undocumented gap. The reachability report proves the three-step budget.
- **Bounded activity ordering.** Recent-first plan ordering no longer reads every
  event into Python, and Active or Finished mode loads only that mode's plans.
- **Status healing and drift.** `reconcile` heals parent status and stale leases,
  `--check` reports the same drift without writing, and `stats` names ambiguous
  rows. `--heal` and `--no-heal` choose automatic repair per command.
- `--no-skills` and `--no-hooks` are remembered across upgrades. Use
  `lpui setup --hooks` to opt back in.
- Headless upgrades, `--json`, `--yes`, and agent calls leave new integrations
  pending with no writes.
- The database schema is unchanged; override audit rows reuse the events table.

### Upgrade

```bash
pipx upgrade lazyplan-tui
```

No manual migration is required.

## v0.34.0 — 2026-11-07

The trust layer and parallel-agent handoff are in the product. Plans can be
approved and diffed, criteria can carry evidence, questions can block
readiness, sessions tag their writes and hand off cleanly, and parallel agents
can avoid the same files.

### Added

- **Approval snapshots and plan diff.** `plan approve`, `plan revisions`, and
  `plan diff` record a revision and show scope changes with reasons. Enforced
  plans gate `plan move --to done` until the drift is approved or overridden.
- **Criterion evidence.** `criterion prove|evidence` records the command, exit
  code, commit, PR, artifact, and actor. `task finish --require-evidence`
  gates on the latest passing row; `audit --min-evidence` reports coverage.
- **Questions and readiness.** `question add|list|resolve|reopen` records
  plan-level ambiguity, and `plan ready` refuses while lint, criterion
  coverage, or open questions fail.
- **Review packet.** `review --plan P` prints one deterministic Markdown
  handoff with the plan, approval, criteria, commits, PRs, findings, and
  questions.
- **Sessions and handoff.** `session start|end|show|list` records a working
  stretch, tags writes, and carries the summary and next action into
  `context` and `brief`.
- **Parallel-safe claims.** Task touch-points make `next` skip overlapping
  claims in the same checkout; a manual claim needs `--force`, and
  `task finish` warns when commit files overlap another open task.
- **External references.** `ref link|list|unlink` stores read-only pointers to
  epics, issues, and docs. Export and import carry them; lazyplan never fetches
  or writes back.
- **Ship note.** `lpui ship --plan P` prints why, what shipped, evidence,
  residual risks, and follow-ups for a PR body or changelog.

### Changed

- The database schema is version 8. Existing databases migrate on open.
- `context` and `brief` include the previous session handoff; hooks remain
  read-only.
- The TUI shows plan references and keeps the Later horizon visible on the
  roadmap page.
- The roadmap marks Foundation, Now, Next, and Later shipped.

## v0.33.0 — 2026-11-06

Plan creation is now one atomic JSON write. `lpui plan apply` creates the plan,
milestones, tasks, and criteria in one transaction; stable keys make retries
no-ops, `--dry-run` previews, and feature, bugfix, and refactor recipes supply
the skeleton. A budgeted `lpui context` packet resumes a session from the
active slice, and the TUI source filter cycle ends with **Focus**.

### Added

- **Plan documents.** `lpui plan apply --file plan.json [--dry-run]` creates a
  complete tree atomically. Stable keys make an identical retry a no-op; a
  failed apply rolls the tree back.
- **Recipes.** `lpui plan recipe feature|bugfix|refactor` prints a JSON
  skeleton with QA, refactoring, and documentation tasks.
- **Context packet.** `lpui context --max-chars N` returns the active plan,
  doing task and claim, next open tasks, open criteria, recent decisions and
  notes, recent commits, unresolved comments, and claims. Available as
  `lazyplan://context` in MCP and in session-start and pre-compact hooks.
- **Focus filter.** The TUI source filter cycle ends with **Focus**: doing,
  claimed, blocked, attention, and next work with parent context.

### Changed

- The database schema is version 2. Existing databases migrate on open; the
  new `entity_keys` table backs idempotent plan apply.
- Session-start and pre-compact hook context now uses the budgeted context
  packet instead of the brief.
- The agent skill, packaged AGENTS contract, usage guide, man page, and site
  roadmap document the new commands.

### Upgrade

```bash
pipx upgrade lazyplan-tui
```

No manual migration is required. The database schema upgrades on open.

## v0.32.0 — 2026-11-03

Windows updates now close lpui before touching the install, apply the wheel
from a detached helper after the process exits, write the full command and
output to a log, and relaunch. This avoids the locked-file failures that could
leave both `lpui upgrade` and the TUI staged apply unable to finish.

### Fixed

- Windows pipx updates use the existing pipx venv's own `python -m pip`
  instead of asking pipx to recreate the venv, so the running interpreter and
  shim are never replaced.
- Windows venv updates use the owning venv's pip through the same detached
  helper.
- The TUI Update screen offers **Restart now** after a download; **Later**
  keeps the stage for the next launch.
- Failed applies leave the old version runnable, park the error, and show the
  full log path on the next launch.
- Stale `applying.json` state is recovered automatically.

### Added

- Full update logs under `%LOCALAPPDATA%\lazyplan\logs\` on Windows.
- `lpui upgrade --diagnose` prints the detected method, owning Python, pipx
  and shim paths, update directory, log directory, and repair command.
- A real Windows smoke job covers pipx and venv success plus a forced
  install failure in isolated homes.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated `README.md`, `docs/usage.md`, `docs/setup.md`,
  `docs/design-system.md`, `src/lazyplan/data/SKILL.md`, and the site.

## v0.31.0 — 2026-11-03

Markdown export is now a deliberate save instead of a fire-and-forget write.
The palette opens a folder picker with the filename ready, starts in your
Downloads folder, and asks before replacing an existing file. The CLI keeps
`--file` and refuses accidental overwrites unless you pass `--force`.

### Added

- **Export plan as Markdown** opens a destination picker with a browsable
  folder tree, editable path, inline errors, and Export/Cancel actions.
- The picker starts in the platform Downloads folder, falls back to the launch
  directory, and prefills `plan-P<id>.md`.
- Existing destinations ask before overwrite; cancel keeps the file, confirm
  replaces it.
- `lpui export --file PATH` creates missing parent folders, resolves `~`, and
  accepts directory targets by writing the default plan filename inside.
- `--force` opts into replacing an existing file. Without it, the command
  exits 2 with the path and the overwrite guidance.
- Exports write through a sibling temporary file, so a failed write never
  truncates an existing export.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated `README.md`, `docs/usage.md`, `docs/design-system.md`,
  `src/lazyplan/data/SKILL.md`, the man page, and the site copy and
  screenshots.

## v0.30.5 — 2026-11-03

The main screen now gives the plan tree and the preview column an equal half
of the width. Tree rows reflow live as the terminal resizes, so long titles
expand or truncate in place instead of keeping stale padding, and shrinking no
longer leaves a horizontal scrollbar behind.

### Changed

- At 100 columns and wider, the plan tree and the side column each take half
  of the main row. Below 100 columns the tree keeps the full width.
- Resizing inside a layout tier re-renders every visible row from cached row
  specs without reloading the database or rebuilding the tree.
- Selection, expanded folds, marks, the doing-row spinner, and the active
  screen survive a resize.
- Crossing the 100-column visibility breakpoint still performs the normal tree
  refresh.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated `README.md`, `docs/usage.md`, `docs/design-system.md`, and the site
  copy and screenshots.

## v0.30.4 — 2026-11-02

The TUI doing spinner now uses the braille dots cycle that most terminal
applications use, so an active plan, milestone, or task shows the familiar
`⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏` animation. Static output keeps the `◐` glyph.

### Changed

- Doing rows in the plan tree animate through the braille dots frames at the
  existing 160ms cadence.
- `LAZYPLAN_NO_SPINNER=1` still freezes the tree on the static `◐`.
- CLI, export, preview, and detail views are unchanged.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated the spinner sections in `docs/usage.md` and
  `docs/design-system.md`.
- Clarified the forced reinstall needed when upgrading from 0.30.1 or
  earlier in `README.md`, `docs/usage.md`, `docs/setup.md`, and the site.

## v0.30.3 — 2026-11-01

The timeline now follows the row under the cursor and shows only that row
plus its immediate children. Clicking a plan shows the plan and its
milestones, clicking a milestone shows the milestone and its tasks, and
clicking a task shows only the task. Ancestors and siblings no longer
appear.

### Changed

- A plan selection renders the plan lane and its milestone lanes.
- A milestone selection renders that milestone and its immediate task lanes.
- A task selection renders only the task lane.
- With no selection the card shows `select a row`; an empty database shows
  `no plans yet`.
- A plan without milestones and a milestone without tasks keep their own
  lane instead of an empty chart.
- The section subtitle follows the scoped plan or the empty state.

### Upgrade

If you are upgrading from 0.30.1 or earlier, use the forced reinstall in the
v0.30.2 notes instead of a plain `pipx upgrade`. Otherwise:

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated the timeline sections in `docs/usage.md` and
  `docs/design-system.md`.

## v0.30.2 — 2026-11-01

Internal architecture refactor. Runtime behavior is unchanged, but the package
layout and console entry points moved, so upgrades from 0.30.1 or earlier need
a forced reinstall. The package is now organized as a pure core, a services
layer, an SQLite store adapter, infrastructure adapters, and a presentation
layer for the TUI, CLI, MCP server, and setup flow.

CLI text, `--porcelain`, `--json`, MCP schemas, share HTML, export output, and
TUI snapshots are unchanged. The database schema is unchanged.

### Upgrade

The refactor changed the package layout and the `lpui`/`lazyplan` console-script
entry points. Upgrading in place from 0.30.1 or earlier is not supported; do a
forced reinstall in the environment that owns `lpui`:

```bash
pipx install --force lazyplan-tui
# or, in a venv
python -m pip install --force-reinstall lazyplan-tui
```

On Windows, add `--backend pip` to the pipx command. `lpui upgrade` and a plain
`pipx upgrade` are safe once you are on 0.30.2 or newer. The database schema
and your data are unchanged.

## v0.30.1 — 2026-11-01

Fixes the timeline's false shared start. Project and milestone traces now begin
when the row enters doing, so sequential milestones show distinct start times
and a pause leaves a visible gap.

### Fixed

- Project and milestone traces start at their first `-> doing` event instead of
  the row's add event.
- A pause splits a project or milestone trace into separate segments; resumed
  work starts a new segment with its own start and finish dots.
- A milestone or plan that never entered doing keeps its lane and legend entry
  but draws no trace.
- Lane start and end follow the first and last doing interval; a never-doing
  lane keeps its add position.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- Updated the timeline sections in `docs/usage.md` and
  `docs/design-system.md`.

## v0.30.0 — 2026-11-01

A visual overhaul for the TUI. The default palette is Catppuccin Mocha, with
Latte and an OLED-black void alongside it; the preview keeps its header fixed
over a real GIT pane; one icon family labels structure; and the timeline card
reads the scoped plan at a glance.

### New

- **Theme overhaul.** The default `lazyplan-dark` theme now draws the
  Catppuccin Mocha palette, `lazyplan-light` draws Latte, and a new OLED-black
  `lazyplan-void` theme is available. `t` cycles mocha → void → latte, and
  `LAZYPLAN_THEME` accepts `mocha`, `void`, `latte`, and the original
  `dark`/`light` names.
- **A real GIT pane.** Under the preview, a compact card shows the selected
  row's linked checkouts, branch, clean/dirty state, ahead/behind counts, the
  newest commits, and pull-request state. It grows with its content and yields
  room back to the preview when nothing is linked.
- **A sticky preview header.** The status/title/breadcrumb stays fixed while
  the reason, scope, next tasks, acceptance, and notes scroll beneath it.
- **Icon language.** Plans, milestones, tasks, sections, checkouts, commits,
  and pull requests now use one consistent single-cell icon family in previews,
  details, and the source trail. Rows keep the canonical
  `GLYPH KIND<id> title` grammar.
- Plan and milestone rows show a compact `▰▰▰▱▱` progress bar beside the
  numeric count. Blocked tasks carry a red `⚑`, and claims a `◉ @actor` chip.
- The plans panel takes 45% of the shell width, leaving 55% for the
  preview/GIT column; the preview keeps the larger share.
- The bottom Gantt is now a rounded `timeline` card at 40% of the shell height
  (11-row minimum, 16-row maximum) with the scoped plan name in its border
  subtitle. Projects, milestones, and focused tasks each get one compact
  swimlane.
- The `plans`, `preview`, `git`, `timeline`, `detail`, `source`, `trail`, and
  `diff` pane titles are lowercase with breathing room, matching the tracker-TUI
  conventions the app borrows from.
- Preview documents no longer repeat the bottom key legend inside the body;
  the preview border carries the `enter open · e edit` hint instead.
- Detail read mode merges the checkout state, commits, files, and pull
  requests into one `git · source` section instead of repeating them across
  separate `git`, `commits`, and `repos` blocks.
- The plans panel no longer renders its non-selectable `plans` root row; plans
  are the top-level rows.
- Task traces cover only `doing` intervals. Todo, paused, and done gaps render
  no line, but the lane and its legend label remain; resumed work shows
  separate segments with start and finish dots.
- Open work shows a `now` marker. The time axis adapts its tick count and
  date/time format to the span, and no-plan or no-milestone states render
  centered copy inside the chart.
- The legend is horizontal at the top, uses `═` for projects, `─` for
  milestones, and `·` for tasks, truncates titles with an ellipsis, and folds
  overflow into `+N more`.
- Selecting a milestone or task adds the focused milestone's task lanes and
  marks the selected task. Large lane sets scroll vertically at one row each.
- Every project, milestone, and task lane keeps a dim full-width baseline so
  each swimlane stays visible even when it is not doing. The lane under the
  cursor renders bold with a heavier glyph (`╍` project, `━` milestone,
  `●` task), and its legend entry is bold without the old `*` suffix. The
  baseline itself is identical for selected and unselected lanes.
- Project and milestone traces now cover their whole start→finish span, so a
  brief pause no longer breaks the line. Task traces still show `doing`
  intervals, so task-level pauses remain visible. The `now` marker appears for
  any open lane, even when it is paused.
- **Stable tree stats.** Plan, milestone, and task rows keep their stats in
  fixed columns, with blank slots for missing values, so the right-hand block
  no longer shifts when a row changes state. Narrow terminals use compact
  forms and drop provenance slots first; task rows show a commit count (`2c`)
  instead of SHAs, and repo detail stays in the preview and GIT pane.
- The Gantt refreshes within the one-second database poll and advances open
  lanes and the now marker every 15 seconds. The Daily activity, Task status,
  and Project progress cards are removed.
- An empty plans panel shows a centered `nothing planned... yet` message
  instead of a blank tree.

### Under the hood

- `tui/theme/tokens.py` defines `DARK_TOKENS`, `LIGHT_TOKENS`, and
  `VOID_TOKENS`; `tui/theme/themes.py` registers all three and resolves the
  `LAZYPLAN_THEME` aliases.
- `views/git.py` builds a pure `GitDocument`; `widgets/git_panel.py` renders it
  under the preview, and `controllers/git_state.py` owns the cached
  branch/dirty snapshot.
- `PreviewDocument` splits `render_head()` from `render_body()` so the panel
  can keep the header fixed while the body scrolls.
- `design/tokens.py` owns `KIND_ICON`, `SECTION_ICON`, and `STATE_ICON`.
- `metrics.snapshot(store, plan_id=..., scope_kind=..., scope_id=...)` derives
  doing intervals from status events, adds focused task lanes, and keeps the
  existing read-only aggregate fields.
- `MetricsController` owns the 120 ms selection debounce, the 15-second now
  tick, and refresh after a tree rebuild.
- `tui/metrics/timeline_layout.py` holds the pure axis, lane, legend, glyph,
  and segment helpers so `TimelineCard` stays a thin Plotext renderer.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.29.0 — 2026-10-31

Live update checks in an open TUI. The status bar keeps the update chip current,
and a release published while the app is open appears within minutes instead of
waiting for the next launch.

### New

- The TUI re-reads the shared update cache every 60 seconds.
- The network check runs at most once every 5 minutes through a shared gate in
  the lazyplan home, so several open instances still make one request.
- A failed check records a 15-minute backoff and keeps using the cached version
  instead of retrying every minute.
- The status chip updates when a newer version appears and clears when the
  installed version catches up. Each version toasts once; a newer version
  toasts again.

### Under the hood

- Added `poll_interval`, `network_interval`, `claim_refresh`, `defer_refresh`,
  and `refresh_update` to `upgrade`.
- `LAZYPLAN_UPDATE_INTERVAL` and `LAZYPLAN_UPDATE_NETWORK_INTERVAL` override the
  cadence; values are clamped, and invalid values fall back to the defaults.
  `LAZYPLAN_NO_UPDATE_CHECK` still disables both checks.
- The update timer stops on unmount, and one guarded worker prevents overlapping
  checks. The CLI notice stays cache-only.
- Tests cover defaults, overrides, clamping, gate contention, backoff, chip
  clearing, and toast semantics.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.28.1 — 2026-10-31

Refuses downgrades in every update path. The staged-update flow and `lpui
upgrade` reject a target older than or equal to the installed version before
any download or installer runs.

### Fixed

- `stage_update` refuses a non-newer target before fetching a wheel.
- `apply_update` and apply-on-launch refuse an older or equal staged version
  without running pipx or pip. A planted older stage is cleared.
- `run_upgrade`, `upgrade_pipx`, and `upgrade_venv` refuse a downgrade before
  building a command.
- The Update screen hides Download when the latest release is not newer, and a
  stale cached notice no longer opens it.
- Tests cover staging, apply, both runners, the screen, and the cached notice.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. Downgrades are intentionally unsupported;
there is no rollback flag.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.28.0 — 2026-10-31

Staged updates in the TUI. When a newer release exists, the status bar shows
`update vX.Y.Z` and `U` opens an Update screen. Download verifies the PyPI wheel
and caches it; the next TUI launch applies it and re-execs into the new version.

### New

- The update notice now names the latest version, and `U` or the **Update lpui**
  palette command opens a dedicated Update screen.
- The screen shows installed and latest versions plus the install method, with
  **Download** and **Later** for pipx and venv installs.
- Download fetches the exact PyPI wheel, verifies its SHA256, and keeps one
  staged slot under the shared home.
- The next TUI launch installs the cached wheel and re-execs before the
  interface opens. Agent and `--json` calls never download or apply.
- rpm, deb, and source installs keep their package-manager or `git pull`
  guidance. A failed download leaves no stage; a failed apply keeps the old
  version runnable and reports one retryable notice.

### Under the hood

- Added `update_stage` with atomic claim, digest re-verification, and pipx/venv
  installers.
- Added headless TUI and cache tests, registered the module with the
  architecture layer guard, and extended the vulture allowlist for Textual
  dispatch.
- Documented the flow, cache paths, recovery, and screen in the usage guide and
  design system.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md#staged-updates-in-the-tui)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.27.2 — 2026-10-31

Removes the redundant source marker from every row. Git integration, commit and
PR links, the source trail, and the database schema are unchanged.

### Changed

- Plan, milestone, task, and source-trail rows no longer end in a marker glyph.
  Commit and PR chips, the preview, and the detail page still show provenance.
- Plain CLI row output drops the same suffix; scripts that parsed it should
  read the chips or `lpui show --files` instead.

### Under the hood

- Deleted the unused marker helpers and branch icon entries, plus the
  row-builder plumbing that only fed them.
- Updated TUI, CLI, and docs tests to assert the remaining chips.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged, and every
existing commit, pull request, and repo link is preserved.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Design system](https://github.com/fluxion-dev/lazyplan/blob/main/docs/design-system.md)
- [Site](https://fluxion-dev.github.io/lazyplan/)

## v0.27.1 — 2026-10-28

Maintenance release for the layered package restructure. CLI commands, TUI
behavior, and the SQLite schema are unchanged; this release is about making the
codebase easier to review, package, and verify.

### Under the hood

- Split the 2,369-line store into focused persistence mixins: plans, tasks,
  claims, annotations, links, repos, views, and shared declarations.
- Split services into plans, claims, tasks, VCS, forge, tree, and transfer
  modules behind the unchanged `lazyplan.services` API.
- Split the CLI into `cli/`, noun-grouped `cli/commands/`, and role-grouped
  `cli/parser/`; renamed the palette registry and published the payload
  serializer.
- Split first-run setup into stage modules and the Textual app into feature
  mixins with a `tui/screens/` package. `design.py` remains the styling source
  of truth.
- Moved the bundled skill and AGENTS text into packaged `lazyplan/data/` and
  split the MCP server into protocol, tool, and resource modules.
- Grouped tests by domain, removed every test `sys.path` edit, and added
  shared `tests/support/` helpers.
- Added architecture guards for import cycles, layer inversions, and a
  600-line module budget.
- Fixed the PEP 639 license metadata, required `setuptools>=77`, pinned
  `textual>=8.2.8,<9`, and added a clean-install smoke gate to `tools/check.sh`.
- Fixed a platform-encoding regression in the download snapshot tests.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. The database schema is unchanged. Back up
first with `lpui export --format json` if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Contributor layout](https://github.com/fluxion-dev/lazyplan/blob/main/CONTRIBUTING.md#project-layout)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## v0.27.0 — 2026-10-27

Windows parity and a performance sweep through the read paths. The coordination,
review, and provenance features from 0.26 are unchanged.

### Windows support

- Install with `pipx install --backend pip lazyplan-tui`; the shared home is
  `%LOCALAPPDATA%\lazyplan` and the default actor is `%USERNAME%`.
- Standard input, output, error, and plan files use UTF-8. Reads accept UTF-8 or
  UTF-16 with a BOM, and writes preserve existing CRLF line endings.
- Claude Code hooks match both `Bash` and `PowerShell` and drop the unsupported
  `PreCompact` event; `SessionStart` re-injects the brief after compaction.
- `lpui upgrade` manages pipx and venv installs on Windows.
- CI runs the full gate suite on Linux, macOS, and Windows.

### Performance

- `tools/perf_bench.py` builds an 88-plan, 789-task fixture and gates exact query
  counts plus generous wall ceilings from `tools/check.sh` on all three platforms.
- On the fixture, tree load falls from 909 queries to 12, `list --json` from
  7,853 to 18, export from 18,612 to 26, audit from 4,740 to 202, and TUI refresh
  from 5,148 to 139.
- Reads batch through bulk maps; the TUI refreshes from one tree snapshot, moves
  git and diff work to workers, and stops rebuilding on view-only changes.
- Read indexes and a schema-version fast path make repeat opens cheaper.
- Update notices are cache-only, so list, show, next, hooks, MCP, and porcelain
  calls make no network request.

### Documentation and site

- README, usage, setup, performance, the bundled agent skill, and the man page
  cover Windows paths, encoding, hooks, upgrades, and the benchmark.
- The homepage has a 0.27 band, a Windows section, a performance section with the
  fixture results, and a PowerShell quickstart. The top navigation collapses into
  Product, Capabilities, and Learn menus, with a mobile panel.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. An existing database picks up the new read
indexes and schema version the first time the CLI opens it. Back up first with
`lpui export --format json` if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Performance and benchmarks](https://github.com/fluxion-dev/lazyplan/blob/main/docs/performance.md)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## v0.26.0 — 2026-10-26

This release turns the plan into a coordination surface: agents claim work
safely, proof stays attached to the row, reviewers can comment, and done can
wait for real evidence.

### Agent coordination

- `lpui next` atomically claims the first eligible todo with a renewable lease.
- `claim take`, `claim renew`, `claim release`, and `claim --force` manage
  specific tasks; expired leases are reclaimable.
- Notes are append-only on plans, milestones, and tasks and appear in `show`,
  `brief`, porcelain, and the TUI preview.
- `task block --reason` and `task unblock` park work without adding a fourth
  status; blocking records the reason and releases the claim.
- The TUI shows active and expired claims, blocked badges, and a `marked` count.

### Flow health

- `lpui stats --since 30.days [--by NAME] [--stale-after 1.days]` reports WIP,
  median cycle time, throughput, aging, stale todos, reopened rows, active
  claims, and blocked tasks.
- Stats support `--json` and six-column porcelain output and never call the
  network.
- The TUI **Attention** source filter surfaces expired claims, blocked tasks,
  aging doing work, done rows with open criteria, and red PR checks.

### Traceability and lint

- `criterion relate` and `criterion unrelate` link acceptance items to proving
  tasks; relations survive export/import.
- `lpui trace --plan|--criterion` walks criterion → task → commit → PR.
- `lpui lint --plan --strict` flags uncovered criteria, missing commit-slice or
  verification tokens, placeholder text, and done rows with open criteria.

### MCP server

- `lpui mcp` serves Model Context Protocol over stdio with no extra dependency.
- Read tools cover the brief, plans, rows, claims, audit, trace, lint, and info;
  write tools cover the journal, criteria, claims, notes, blocked work, and
  commit links.
- Resources expose `lazyplan://brief` and `lazyplan://plan/{id}`.
- `--read-only` hides and rejects writes and never creates a missing database.

### Collaboration

- Comments support add/list/resolve/unresolve and `@mention` filtering on plans,
  milestones, and tasks; unresolved comments appear in the detail pane.
- `lpui share --plan P` writes escaped HTML or safe JSON snapshots with no
  tokens, auth state, raw payloads, or cache records.
- Plans carry stable UIDs, generated for existing databases.
- `lpui sync --file dump.json [--dry-run]` adds unknown plans, skips identical
  plans, and reports conflicts without deleting or overwriting local work.
- Sync is plan-granularity; row-level merge is intentionally out of scope.

### Completion gates

- `task finish --require-pr` needs at least one linked pull request.
- `task finish --require-checks` needs every linked PR's cached checks to be
  `pass`, `neutral`, or `skipped`.
- Gates read cached state only; run `pr refresh` to update it. A failure exits 2
  and leaves the task doing with no commits linked.
- `--override REASON` records the actor, reason, and gate state, then completes.
- `task start` rejects a branch already recorded on another open task in the
  same checkout or remote and names the owner.

### Issue imports

- `lpui issue import --provider github --repo OWNER/REPO` imports live issues
  and skips pull requests.
- `lpui issue import --provider linear --file export.json` imports a Linear JSON
  export.
- `--as plan|task`, `--milestone`, and `--dry-run` control placement and writes.
- Re-import dedupes by provider + external id and refreshes cached source
  metadata only; imports are one-way with no writeback and no raw payloads.

### Search and bulk edit

- `/` searches titles, descriptions, why/what, notes, comments, claim actors,
  blocked reasons, and issue refs.
- `space` marks rows; marks survive refresh and are session-only.
- Palette bulk actions move marked tasks to doing/done, block with a reason,
  release claims, clear marks, and undo the last status/block change once.
- Bulk delete and archive remain single-row because undo cannot safely recreate
  subtrees.

### Upgrade

```bash
pipx upgrade lazyplan-tui
# or
pipx install --force lazyplan-tui
```

No manual migration is required. Existing databases gain plan UIDs and the new
tables when the CLI opens them. Back up first with `lpui export --format json`
if you want a restore point.

### Documentation

- [Usage guide](https://github.com/fluxion-dev/lazyplan/blob/main/docs/usage.md)
- [Setup walkthrough](https://github.com/fluxion-dev/lazyplan/blob/main/docs/setup.md)
- [Site and screenshots](https://fluxion-dev.github.io/lazyplan/)

## Earlier releases

See [GitHub releases](https://github.com/fluxion-dev/lazyplan/releases) for
v0.25.0 and earlier.
