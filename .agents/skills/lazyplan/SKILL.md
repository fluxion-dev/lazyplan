---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — projects, stories, tasks, proposals. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# lazyplan (`lpui`) — repo issue tracker

`lpui` is the repo's plan of record: projects > stories > tasks, stored in
`.plan/lazyplan.db` (SQLite, committed with the repo or local — check
`.plan/config.json`). The human watches `lpui ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lpui`.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode add-task ...`). Reads don't need it.
`--actor` and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`).

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → enclosing git repo's `.plan/lazyplan.db` →
global `~/.local/share/lazyplan/lazyplan.db`. Running from any subdirectory
of the repo resolves to that repo's DB. Don't override `--db` unless asked.

## Read first

```bash
lpui list [--status todo|doing|done] [--project ID] [--owner NAME]  # tree
lpui show --kind project|story|task --id N                          # full context
lpui gantt [--tasks] [--width 40]                                   # timeline
lpui feed --limit 20                                                # recent activity
lpui export --format json                                           # full dump when you need everything
lpui info                                                           # resolved db path + scope + counts (scope debugging)
```

Add `--json` for machine-parseable output (`lpui list --json`).

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is project|story|task everywhere it appears.

```bash
lpui --actor NAME add-project --name "API v2" [--goal .. --metrics .. --scope-in .. --scope-out ..]
lpui --actor NAME add-story --project P --title "Feature Y" [--owner me --priority p0 --estimate 2w]
lpui --actor NAME add-task --story S --title "Do X" [--desc ctx --owner me --priority p1 --estimate 2d]
lpui --actor NAME update --kind task --id T [--title .. --desc .. --owner .. --priority p0|none --estimate ..]
lpui --actor NAME status --kind task --id T --to doing|done
lpui --actor NAME delete --kind task --id T                         # immediate, no confirm
```

Deleting a project removes its stories and tasks — double-check ids first.
Closing with open acceptance criteria warns but never blocks.

## Checklists, links, risks, milestones

```bash
lpui --actor NAME add-criteria --kind task --id T --text "Works offline"  # acceptance item
lpui criteria --kind task --id T                                          # list items
lpui --actor NAME check --id C / lpui --actor NAME uncheck --id C                 # tick/untick (advisory)
lpui --actor NAME delete-criteria --id C
lpui --actor NAME add-link --kind task --id T --url URL [--label spec]    # attach reference
lpui links --kind task --id T                                             # list links
lpui --actor NAME delete-link --id L
lpui --actor NAME add-risk --project P --title "Slip" [--likelihood high --impact high --mitigation buf]
lpui risks --project P                                                    # likelihood x impact first
lpui --actor NAME risk-status --id R --to mitigated
lpui --actor NAME add-milestone --project P --title "Beta" --date 2026-11-15
lpui milestones --project P                                               # list markers
lpui --actor NAME delete-milestone --id M
lpui --actor NAME import --file dump.json                                 # load an export dump (remaps ids)
```

## Human-in-the-loop (preferred for judgment calls)

```bash
lpui --actor NAME propose --kind task --parent S --title "Refactor X"  # parent: story id for tasks, project id for stories
lpui --actor NAME ask --question "Which scope: minimal or full?"       # human answers in UI
lpui questions --all          # check for answers (poll; agents: lpui feed --json --follow &)
lpui proposals --status pending
```

Propose/ask instead of guessing when scope, taste, or repo-wide impact is
involved. The human approves (`4` then `a`/`x` in `lpui ui`). Never
`approve`/`reject` your own proposals or `answer` your own questions —
those verbs belong to the human in the UI.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent project/story ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- Full verb reference: `lpui --help` (CLI == TUI `:` command bar).
