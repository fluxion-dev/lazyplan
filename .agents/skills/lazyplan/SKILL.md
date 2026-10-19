---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — interview for a project's why/what/acceptance criteria, then cut prioritized stories and tasks. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# lazyplan (`lpui`) — local project journal

`lpui` is the repo's plan of record: projects > stories > tasks, stored in
`.plan/lazyplan.db` (SQLite, committed with the repo or local — check
`.plan/config.json`). The human watches `lpui ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lpui`.

A project is: title + priority + why + what + acceptance criteria. Stories cut
a project into slices; tasks cut a story into prioritized units of work. That
is the whole model — no dates, owners, labels, or estimates.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode add-task ...`). Reads don't need it.
`--actor` and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`).

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → enclosing git repo's `.plan/lazyplan.db` →
global `~/.local/share/lazyplan/lazyplan.db`. Running from any subdirectory
of the repo resolves to that repo's DB. Don't override `--db` unless asked.

## Starting a project: interview first

Never invent a project's why/what/acceptance criteria. When the user asks to
plan something, interview them before writing anything:

1. Ask why this exists (one or two sentences).
2. Ask what gets built (scope in plain language).
3. Ask for acceptance criteria (how we know it is done).
4. Confirm the title and priority (p0 highest, p3 lowest).

Then record the definition:

```bash
lpui --actor NAME add-project --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-criteria --kind project --id P --text "Works offline"
lpui criteria --kind project --id P                                     # list items
lpui check --id C / lpui uncheck --id C                                 # tick/untick (advisory)
```

Only once the definition is agreed, cut the work — stories from the project,
then prioritized tasks from each story:

```bash
lpui --actor NAME add-story --project P --title "Feature Y" --desc ".." --priority p1
lpui --actor NAME add-task --story S --title "Do X" --desc "context" --priority p0
```

Work top priority first. Move rows through todo → doing → done as you go.

## Read first

```bash
lpui list [--status todo|doing|done] [--project ID] [--priority p0]  # tree
lpui show --kind project|story|task --id N                           # full context
lpui feed --limit 20                                                 # recent activity
lpui export --format json                                            # full dump when you need everything
lpui info                                                            # resolved db path + counts (scope debugging)
```

Add `--json` for machine-parseable output (`lpui list --json`).

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is project|story|task everywhere it appears.

```bash
lpui --actor NAME add-project --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-story --project P --title "Feature Y" [--desc .. --priority p0]
lpui --actor NAME add-task --story S --title "Do X" [--desc ctx --priority p1]
lpui --actor NAME update --kind task --id T [--title .. --desc .. --priority p0|none]
lpui --actor NAME update --kind project --id P [--title .. --what .. --why .. --priority p0|none]
lpui --actor NAME status --kind task --id T --to doing|done
lpui --actor NAME delete --kind task --id T                          # immediate, no confirm
```

Deleting a project removes its stories and tasks — double-check ids first.
Closing with open acceptance criteria warns but never blocks.

## Acceptance criteria

```bash
lpui --actor NAME add-criteria --kind project --id P --text "Works offline"  # acceptance item
lpui criteria --kind project --id P                                          # list items
lpui check --id C / lpui uncheck --id C                                      # tick/untick (advisory)
lpui --actor NAME delete-criteria --id C
lpui --actor NAME import --file dump.json                                    # load an export dump (remaps ids)
```

Criteria live on projects, stories, and tasks. Project-level criteria are the
definition of done — tick them as the work lands.

## Human-in-the-loop (preferred for judgment calls)

Scope, taste, and repo-wide impact belong to the human: ask in conversation
and wait for an answer before writing. Never decide a project's why/what or
its acceptance criteria on your own — interview, record, confirm. Status moves
and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent project/story ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is keyboard-only).
