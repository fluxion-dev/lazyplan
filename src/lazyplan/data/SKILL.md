---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — interview for a plan's why/what/acceptance criteria, cut milestones and tasks, and keep the journal accurate while implementing. Use when the user asks to plan work, track progress, break down a feature, check status, implement or continue planned work, resume a task, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# lazyplan (`lpui`) — local plan journal

`lpui` is the repo's plan of record: plans > milestones > tasks, stored in
`.agents/lazyplan/lazyplan.db` (SQLite, committed with the repo or local — check
`.agents/lazyplan/config.json`). The human watches `lpui ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lpui`.

A plan is: title + why + what + acceptance criteria. Milestones cut
a plan into slices; tasks cut a milestone into units of work. That
is the whole model — no dates, owners, labels, or estimates.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode task add ...`). Reads don't need it.
`--actor`, `--porcelain`, and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`). In an active loop, pass
`--porcelain`: writes answer with one tab-separated row and overview reads
stay glyph-free. `--json` wins when both are present; use it only when you
need fields porcelain does not carry.

If your host supports MCP, use the local `lpui mcp` server (or
`lpui mcp --read-only` for reviews); otherwise use `--porcelain` on every
call. Start work with `lpui next --porcelain`: it claims the first eligible todo
and moves it doing. A claim is a lease, not an owner. Renew it while you work,
release it when you stop, and note handoffs with `lpui note add`.

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → nearest repo-owned
`.agents/lazyplan/lazyplan.db` walking up → shared `~/.lazyplan/lazyplan.db`.
On Windows the shared home `~/.lazyplan/` is `%LOCALAPPDATA%/lazyplan/`
everywhere below, and the default actor is `%USERNAME%` (`$USER` elsewhere).
Plan text is read as UTF-8 or UTF-16 with a BOM and written as UTF-8.

Setup runs on first use. It detects agents, installs or refreshes their
skills, and remembers the result in `~/.lazyplan/setup.json`. The default is
the shared home database and no repo files. `lpui setup --placement repo`
opts the current checkout into `.agents/lazyplan/` plus repo skills,
templates, an `AGENTS.md` pointer, and gitignore entries. `--db` and
`$LAZYPLAN_DB` always win and are never moved.

`lpui doctor` reports the resolved layout and any findings without writing
(exit 0 clean, 1 misplaced). On upgrade, setup offers once to move an
untracked repo database home, remembers keep/never, never offers to move a
tracked database, and refuses to merge two databases that both hold plans.
Every touched file is backed up under `~/.lazyplan/backups/<timestamp>/`.
Agent commands never prompt; only `lpui`, `lpui setup`, and `lpui upgrade`
do. Don't override `--db` unless asked.

## Linked repos (central plan, many checkouts)

Plans, milestones, and tasks each link 0..n repo checkouts so one central
DB can plan work across repos. A row with no explicit links inherits:
a task inherits its milestone's effective repos, a milestone inherits its
plan's. Link by absolute checkout path plus remote URL (auto-detected
from `git remote get-url origin` when omitted):

```bash
lpui --actor NAME link-repo --kind plan --id P --repo /path/to/checkout [--remote URL]
lpui --actor NAME unlink-repo --kind plan --id P --repo /path/to/checkout
lpui repos --kind task --id T [--effective]    # explicit vs inherited
lpui list --repo /path/to/checkout             # only matching rows
```

`show` and `list --json` include `repos` plus `effective_repos`;
`export --format json` carries explicit `repos` (import round-trip).

## Git proof

Rows can carry the exact commits that shipped them, including changed files.
`link` attaches HEAD, or a SHA, from the current checkout; `--repo PATH` reads
a different linked checkout. `commits` lists direct and inherited commits, and
`--refresh` re-resolves cached metadata/files and marks missing commits
`[stale]`. Add `--files` to `show` or `commits` to list paths.

```bash
lpui --actor NAME link --kind task --id T [--sha SHA] [--repo PATH]
lpui commits --kind task --id T [--refresh] [--files]
lpui show --kind task --id T [--files]
lpui git status --kind task --id T [--json]
lpui git scan --since 7.days [--dry-run] [--repo PATH]
```

`task start` sets a task doing and records an existing branch plus its base. It
uses the current branch unless `--branch NAME` names another existing branch.
lazyplan never creates or checks out branches and never creates worktrees; use
your VCS tool for that first. `task finish` links `base..HEAD` and moves the
task to done only when the tree is clean. lazyplan never commits, pushes,
fetches, or merges. Commit messages can also carry a `Lazyplan: T12` trailer,
and a `task/12-*` branch attributes commits in its base..HEAD range.

Marking a row done links HEAD only when the tree is clean and HEAD is not
already linked to another row. A task with a started branch must be on that
branch and the commit must be on the task branch history; otherwise lpui warns
and leaves the link for you. `show` includes inherited commits, stale markers,
and web URLs when the origin remote can be mapped.

In the TUI, select a row and press `g` (or use **Open source trail**) to browse
repo → commit → changed file plus linked PRs. The tree uses the same `j`/`k`,
`left`/`right`, click-select, and click-arrow gestures as the main tree.
Highlighting a commit or file renders a read-only unified diff with line
numbers; large diffs stop at 20
files / 300 lines with a `+N more` notice, and `o` opens the full commit.
Binary, root, merge, empty, and missing states are explicit. Diffs are read
live and never persisted. Rows with source details end in a single-cell `⎇`
marker. `o` opens, `y` copies, `/` filters. Plans and milestones aggregate
descendant work. `F` cycles source filters: all, linked, has PR, stale,
unlinked, claims, blocked, attention.

## GitHub pull requests

GitHub support is read-only and opt-in. lpui maps each linked checkout's origin
remote to a `github.com` owner/repo and caches pull requests, checks, and reviews
locally. `list`, `show`, and opening the screen never call GitHub; only
`pr refresh` does.

Auth precedence: `LAZYPLAN_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, then
`gh auth token`. Tokens never enter the database, export, feed, or logs.

```bash
lpui --actor NAME pr auth
lpui --actor NAME pr status --kind task --id T
lpui --actor NAME pr refresh --kind task --id T
lpui --actor NAME pr list --kind task --id T
lpui --actor NAME pr link --kind task --id T --url https://github.com/org/repo/pull/7
lpui --actor NAME pr unlink --kind task --id T --number 7
```

`pr refresh` links each PR to the task that owns its commit or branch and caches
state, checks, reviews, base/head refs, and merge metadata. Requests reuse ETags
and fall back to cached data offline; stale data is marked. `pr link` is offline
and manual. `show` rolls PRs up from tasks to milestones and plans, task rows
show a PR chip, and detail lists the PR URL. Scope is github.com only. lazyplan
never creates branches, worktrees, commits, pushes, PRs, reviews, comments, or
merges; other tools own those actions.

## Starting a plan: interview first

Never invent a plan's definition. When the user asks to plan something,
interview them before writing anything. A solid definition covers:

- Vision: why this exists (one or two sentences) — the problem and the value.
- Scope: explicit in-scope and out-of-scope lists, in plain language. Push
  until both lists are concrete — vague scope is rejected, not recorded.
- Deliverables: tangible outputs and their order.
- Commit strategy: the ordered slices of small commits that will land the
  work, and the check that keeps each commit green. A plan that cannot name
  its slices is not ready to cut.
- Constraints: technical or operational limits, plus assumptions.
- Success metrics: measurable outcomes that mean it worked.
- Acceptance criteria: how we know it is done.
- Quality: ask whether QA testing, refactoring, and documentation cleanup
  steps should be included, and ask what testing is relevant to the changes
  being made. All three are included by default — only an explicit opt-out
  excludes them.

Fold vision into `--why`; scope, deliverables, commit strategy, constraints,
and metrics into `--what`; acceptance criteria become plan-level checklist
items. There are no stakeholder, owner, or estimate fields — if it does not
fit why, what, or criteria, it does not belong in the definition.

## Implementation requests: close the ambiguity gap

When the user asks to build, implement, or change something, run the
interview above as an ambiguity hunt before writing any row. Do not accept
"implement X" at face value — pin down all of these in conversation:

- Scope: explicit in-scope and out-of-scope lists, in plain language.
- Touch-points: the files, commands, and surfaces involved (scouted, real paths).
- Edge cases and non-goals: what must keep working, what is explicitly excluded.
- Assumptions: what you take for granted, stated so the human can correct it.

Vague scope is rejected, not recorded. No row is written from unscouted
ground, in any case, no exceptions.

## Readability: structure every row

Write every plan why/what, milestone desc, and task desc for scanning:
short paragraphs separated by blank lines, sections with headers or lists
where needed. Creation rejects long single-blob text (over 300 chars with
no paragraph breaks or section markers) — split it into paragraphs and
sections. Short one-liners stay legal. Never ship bracket, example, or
placeholder text as content or criteria — starters ship empty on purpose,
and the interview must fill them with real words.

While interviewing, scout the codebase (explore agents, grep, file reads) so
each question clears up real ambiguity: what exists, what constrains the
approach, what the deliverables touch. Never cut work from an unscouted
definition. Scouting is mandatory before creating anything — plan, milestone,
or task. No row is written from unscouted ground, in any case, no exceptions.
Then record it:

```bash
lpui --actor NAME plan add --title "API v2" --why ".." --what ".."
lpui --actor NAME criterion add --kind plan --id P --text "Works offline"
lpui criterion list --kind plan --id P                                     # list items
lpui criterion tick --id C / lpui criterion untick --id C                                 # tick/untick (advisory)
```

Only once the definition is agreed, cut the work — milestones from the plan,
then tasks from each milestone, shaped as below plus the default QA,
refactor, and documentation tasks.

Every plan carries QA testing tasks, a refactoring task, and documentation
cleanup by default, shaped by the interview's testing answer. Ground every QA task in the acceptance criteria: each criterion is exercised by a named test task, and DoD checklists reference the criteria they satisfy. Only an explicit user opt-out ("skip QA", "no refactoring") excludes them — silence means include.

Work top-down in creation order. Commit each task as it completes — or in a
tight series of green commits — then link it and move it through todo → doing
→ done. Do not defer commits to the end of the plan.

## Review gate: plan is truth

Once the definition is recorded and the work is cut, present the plan for check-off before implementing anything:

```bash
lpui list --status all                 # the whole tree
lpui plan show --id P        # why/what + criteria + children
```

Walk the human through every milestone and task, make last edits on the spot, and start executing only on explicit check-off. Relate every plan criterion to at least one proving task (`lpui criterion relate --id C --task T`) and run `lpui lint --plan P` before check-off. Check that the plan names its commit strategy and that every task desc names its expected commit slice and verification; reject a plan that batches a whole milestone or plan into one commit. During execution the plan stays the truth: fold new findings into the plan before changing code, never around it.

## During execution

Update the journal as you go, not at the end:

```bash
lpui --porcelain next                          # claim the first eligible todo
lpui --porcelain claim renew --id T --ttl 30m  # lease heartbeat while working
lpui --porcelain note add --kind task --id T --text "Decision or handoff"
lpui --actor T --porcelain link --kind task --id T       # after each commit (or `task finish`)
lpui --actor T --porcelain task move --id T --to done    # when the task's slice is complete
lpui --porcelain task block --id T --reason "waiting"    # release the lease and park it
lpui --porcelain audit --since 7.days                    # coverage, lag, and criteria gaps at the end
```

Porcelain rows are `kind<TAB>id<TAB>status<TAB>title<TAB>parent<TAB>extra`.
Parse them by splitting on tabs; never scrape the human text. Set
`LAZYPLAN_PORCELAIN=1` for a whole agent session instead of passing the flag
on every call. Reach for `--json` only when you need full-fidelity fields.

- Never batch a whole plan or milestone into one commit; link each green commit to its task.
- Tick task and plan criteria as they are proven, before closing the row.
- Lifecycle hooks may remind you at session start, after a commit, and before compaction. Hooks are read-only: they never move a task or link a commit for you.
- `lpui claims` / `lpui who` shows active leases. `claim release --force` and `claim --force` record a takeover; blocked work is skipped by `next`.
- `lpui trace --plan P` walks each criterion to its proving task, commits, and PRs. `lpui lint --plan P --strict` rejects uncovered criteria, missing slices or verification, placeholders, and done rows with open criteria.
- `lpui stats --since 7.days` reports WIP, cycle time, throughput, aging, stale work, reopened rows, claims, and blocked tasks. The human screen's Attention filter surfaces the same risk categories.
- Finish with `task finish --require-pr --require-checks` when the task must prove PR/CI evidence; `--override REASON` records an exception. A branch already recorded on another open task is rejected.
- Import issues once with `issue import` (GitHub live or Linear export); re-import refreshes source metadata only and never writes back.
- Human screen: space marks rows; the palette has bulk move/block/release, clear marks, and one undo for status/block changes.
- Collaborate with `comment add/list/resolve`; use `share --plan P` for a read-only snapshot and `sync --file dump.json --dry-run` for a plan-level merge.
- `lpui audit --strict` is the opt-in CI gate; it defaults to 80% coverage, one commit of lag, and zero criteria gaps. Add `--min-trace 0.8` to gate criterion coverage.

## Read first

```bash
lpui --porcelain list --tree [--status todo|doing|done|all]      # plan/milestone/task rows
lpui --porcelain next                                                        # first todo, claimed
lpui --porcelain claims                                                      # active leases
lpui --porcelain brief                                                       # active plan + next update
lpui --porcelain audit --since 7.days                                        # accuracy metrics
lpui --porcelain plan show --id N                                            # definition + criteria + children
lpui --porcelain trace --plan N                                              # criterion -> task -> commit/PR
lpui --porcelain lint --plan N                                               # plan-quality findings
lpui --porcelain stats --since 7.days                                        # flow health
lpui --porcelain feed --limit 20                                                 # recent activity
lpui export --format json                                            # full dump when you need everything
lpui export --format markdown --plan ID [--file out.md]              # one full-fidelity plan doc
lpui info                                                            # resolved db path + counts (scope debugging)
lpui reconcile                                                       # recompute parent statuses from children
```

Use `--porcelain` for the active loop: one tab-separated row per record with
no glyphs or provenance noise. Use `--json` when you need full fidelity
(`lpui list --json`).

## Templates (per-repo creation defaults)

`.agents/lazyplan/templates/{plan,milestone,task}.md` (scaffolded by
`lpui setup --placement repo`; commit them to share) define what new rows look
like. Repo placement shares them; otherwise templates live beside the shared
home DB at `~/.lazyplan/templates/`.
Each file is Markdown
with YAML frontmatter; the body is guidance and ignored:

```yaml
defaults: {why: "", what: ""}   # filled when a flag is empty
required: [title]                             # must be non-empty after fill
criteria: []                                  # starters ship empty: add real criteria per row
```

Long single-blob `why`/`what`/`desc` (over 300 chars with no paragraph
breaks or section markers) fails creation — use paragraphs and sections.
Field names are per kind: plan `title/why/what`, milestone and task
`title/desc`. Missing `required` entries fail with exit 2 naming the
field; missing template files mean legacy behavior (tasks default `p1`).

Setup writes the opinionated starters silently; edit the files to change what
new rows require. Existing edits are never overwritten.

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is plan|milestone|task everywhere it appears.

```bash
lpui --actor NAME plan add --title "API v2" --why ".." --what ".."
lpui --actor NAME milestone add --plan P --title "Feature Y" [--desc ..]
lpui --actor NAME task add --milestone S --title "Do X" [--desc ctx]
lpui --actor NAME task edit --id T [--title .. --desc ..]
lpui --actor NAME plan edit --id P [--title .. --what .. --why ..]
lpui --actor NAME task move --id T --to doing|done
lpui --actor NAME task delete --id T                          # immediate, no confirm
```

Deleting a plan removes its milestones and tasks — double-check ids first.
Status moves roll parents up automatically: closing the last open task
completes its milestone and plan. Closing with open acceptance criteria warns
but never blocks.

## Acceptance criteria

```bash
lpui --actor NAME criterion add --kind plan --id P --text "Works offline"  # acceptance item
lpui criterion list --kind plan --id P                                          # list items
lpui criterion tick --id C / lpui criterion untick --id C                                      # tick/untick (advisory)
lpui --actor NAME criterion delete --id C
lpui --actor NAME import --file dump.json                                    # load an export dump (remaps ids)
```

Criteria live on plans, milestones, and tasks. Plan-level criteria are the
definition of done — tick them as the work lands.

## Milestone standard

Each milestone states user value in narrative form, with testable criteria:

```bash
lpui --actor NAME milestone add --plan P --title "Feature Y" --desc "As a [persona], I want [action] so that [benefit]"
lpui --actor NAME criterion add --kind milestone --id S --text "Given [context], when [action], then [outcome]"
```

Keep milestones INVEST: independent, negotiable, valuable, estimable, small,
testable. At creation, `--desc` carries the narrative plus the INVEST check,
the inputs/prerequisites, and the ordered commit slices; a milestone without them is not ready to cut. Each task advances one small, green commit series; a milestone that only works as one batch commit is not ready. No dependency,
estimate, or owner fields — sequencing lives in creation order (work p0 first),
context lives in `--desc`.

## Task standard

Task titles start with a verb and name the target. `--desc` carries the
technical how: approach, code references, inputs and prerequisites. Task-level
checklists are the definition of done:

```bash
lpui --actor NAME task add --milestone S --title "Implement token rotation" --desc "Approach and file refs"
lpui --actor NAME task add --milestone S --title "Run the relevant test suites" --desc "Suites named in the interview"
lpui --actor NAME task add --milestone S --title "Refactor what the change touched" --desc "Leave the area cleaner"
lpui --actor NAME task add --milestone S --title "Clean up touched documentation" --desc "Docs matching the final code"
lpui --actor NAME criterion add --kind task --id T --text "Unit tests pass"
```

Each task lands as one or more small commits. Every commit is green — the
relevant checks pass and the tree builds — and independently reviewable. Keep
behavior, tests, docs, and refactors in separate commits when they can stand
alone. Never batch a whole milestone or plan into one commit. The task `--desc`
names the expected commit slice and the verification for each commit. Link commits after the fact with `lpui link` or `task finish`; no commit trailer is required.

No assignee or effort fields — ownership is the `--actor` on each write, size
is its position in the list. Every task `--desc` names the technical approach, the inputs/prerequisites, and the expected commit slice — a task missing any of them is not ready to cut. Cut tasks only from scouted ground: each one must
name real files, real constraints, real prerequisites.

## Human-in-the-loop (preferred for judgment calls)

Scope, taste, and repo-wide impact belong to the human: ask in conversation
and wait for an answer before writing. Never decide a plan's why/what or its acceptance criteria on your own — interview, record, confirm. Scout the codebase during the interview to target real files and constraints. Status moves and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent plan/milestone ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- The plan is the truth for the desired implementation: change it before changing course.
- Format for scanability: short headers, fenced code blocks, one concern per block, verdict first.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is keyboard-only).
