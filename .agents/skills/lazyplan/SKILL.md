---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — interview for a project's why/what/acceptance criteria, then cut prioritized stories and tasks. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# lazyplan (`lpui`) — local project journal

`lpui` is the repo's plan of record: projects > stories > tasks, stored in
`.agents/plan/lazyplan.db` (SQLite, committed with the repo or local — check
`.agents/plan/config.json`). The human watches `lpui ui`; agents inject work through
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

`--db PATH` → `$LAZYPLAN_DB` → enclosing git repo's `.agents/plan/lazyplan.db` →
global `~/.local/share/lazyplan/lazyplan.db`. Running from any subdirectory
of the repo resolves to that repo's DB. Don't override `--db` unless asked.

## Starting a project: interview first

Never invent a project's definition. When the user asks to plan something,
interview them before writing anything. A solid definition covers:

- Vision: why this exists (one or two sentences) — the problem and the value.
- Scope: explicit in-scope and out-of-scope lists, in plain language. Push
  until both lists are concrete — vague scope is rejected, not recorded.
- Deliverables: tangible outputs and their order.
- Constraints: technical or operational limits, plus assumptions.
- Success metrics: measurable outcomes that mean it worked.
- Acceptance criteria: how we know it is done.
- Quality: ask whether QA testing, refactoring, and documentation cleanup
  steps should be included, and ask what testing is relevant to the changes
  being made. All three are included by default — only an explicit opt-out
  excludes them.

Fold vision into `--why`; scope, deliverables, constraints, and metrics into
`--what`; acceptance criteria become project-level checklist items. There are
no stakeholder, owner, or estimate fields — if it does not fit why, what, or
criteria, it does not belong in the definition.

While interviewing, scout the codebase (explore agents, grep, file reads) so
each question clears up real ambiguity: what exists, what constrains the
approach, what the deliverables touch. Never cut work from an unscouted
definition. Scouting is mandatory before creating anything — project, story,
or task. No row is written from unscouted ground, in any case, no exceptions.
Then record it:

```bash
lpui --actor NAME add-project --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-criteria --kind project --id P --text "Works offline"
lpui criteria --kind project --id P                                     # list items
lpui check --id C / lpui uncheck --id C                                 # tick/untick (advisory)
```

Only once the definition is agreed, cut the work — stories from the project,
then prioritized tasks from each story, shaped as below plus the default QA,
refactor, and documentation tasks.

Every plan carries QA testing tasks, a refactoring task, and documentation
cleanup by default, shaped by the interview's testing answer. Ground every QA task in the acceptance criteria: each criterion is exercised by a named test task, and DoD checklists reference the criteria they satisfy. Only an explicit user opt-out ("skip QA", "no refactoring") excludes them — silence means include.

Work top priority first. Move rows through todo → doing → done as you go.

## Review gate: plan is truth

Once the definition is recorded and the work is cut, present the plan for check-off before implementing anything:

```bash
lpui list --status all                 # the whole tree
lpui show --kind project --id P        # why/what + criteria + children
```

Walk the human through every story and task, make last edits on the spot, and start executing only on explicit check-off. During execution the plan stays the truth: fold new findings into the plan before changing code, never around it.

## Read first

```bash
lpui list [--status todo|doing|done|all] [--archived] [--project ID] [--priority p0]  # tree (default: all)
lpui show --kind project|story|task --id N                           # full context
lpui feed --limit 20                                                 # recent activity
lpui export --format json                                            # full dump when you need everything
lpui info                                                            # resolved db path + counts (scope debugging)
lpui reconcile                                                       # recompute parent statuses from children
```

Add `--json` for machine-parseable output (`lpui list --json`).

## Templates (per-repo creation defaults)

`.agents/plan/templates/{project,story,task}.md` (scaffolded by `lpui init`,
commit them to share) define what new rows look like. Each file is Markdown
with YAML frontmatter; the body is guidance and ignored:

```yaml
defaults: {why: "", what: "", priority: ""}   # filled when a flag is empty
required: [title]                             # must be non-empty after fill
criteria: ["Works offline"]                   # auto-added rows on create
```

Field names are per kind: project `title/why/what/priority`, story and task
`title/desc/priority`. Missing `required` entries fail with exit 2 naming the
field; missing template files mean legacy behavior (tasks default `p1`).

`lpui init` walks the user through template setup: on a TTY it asks four
convention questions (require project why/what, require story/task desc,
example starter criteria, default task priority) and writes tailored
starters; `--yes`/`--json`/non-TTY writes the opinionated defaults silently.
Rerunning `init` on a TTY offers per-file keep/edit/reset (default keep) —
edits are never overwritten without an explicit reset.

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
Status moves roll parents up automatically: closing the last open task
completes its story and project. Closing with open acceptance criteria warns
but never blocks.

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

## Story standard

Each story states user value in narrative form, with testable criteria:

```bash
lpui --actor NAME add-story --project P --title "Feature Y" --desc "As a [persona], I want [action] so that [benefit]" --priority p1
lpui --actor NAME add-criteria --kind story --id S --text "Given [context], when [action], then [outcome]"
```

Keep stories INVEST: independent, negotiable, valuable, estimable, small,
testable. At creation, `--desc` carries the narrative plus the INVEST check
and the inputs/prerequisites — a story without them is not ready to cut. No
dependency, estimate, or owner fields — sequencing lives in priority order
(work p0 first), context lives in `--desc`.

## Task standard

Task titles start with a verb and name the target. `--desc` carries the
technical how: approach, code references, inputs and prerequisites. Task-level
checklists are the definition of done:

```bash
lpui --actor NAME add-task --story S --title "Implement token rotation" --desc "Approach and file refs" --priority p0
lpui --actor NAME add-task --story S --title "Run the relevant test suites" --desc "Suites named in the interview" --priority p1
lpui --actor NAME add-task --story S --title "Refactor what the change touched" --desc "Leave the area cleaner" --priority p2
lpui --actor NAME add-task --story S --title "Clean up touched documentation" --desc "Docs matching the final code" --priority p2
lpui --actor NAME add-criteria --kind task --id T --text "Unit tests pass"
```

No assignee or effort fields — ownership is the `--actor` on each write, size
is the priority. Every task `--desc` names the technical approach and the inputs/prerequisites — a task missing either is not ready to cut. Cut tasks only from scouted ground: each one must name real files, real constraints, real prerequisites.

## Human-in-the-loop (preferred for judgment calls)

Scope, taste, and repo-wide impact belong to the human: ask in conversation
and wait for an answer before writing. Never decide a project's why/what or its acceptance criteria on your own — interview, record, confirm. Scout the codebase during the interview to target real files and constraints. Status moves and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent project/story ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- The plan is the truth for the desired implementation: change it before changing course.
- Format for scanability: short headers, fenced code blocks, one concern per block, verdict first.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is keyboard-only).
